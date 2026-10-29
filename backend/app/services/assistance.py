"""Gateway estreito para provedores assistidos opcionais.

O restante da aplicação não conhece SDK, modelo ou fornecedor. O gateway
configurado deve responder JSON e nunca é chamado quando a feature flag está
desligada. Exceções viram códigos técnicos; conteúdo do aluno não entra no log.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


class ProviderFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    words: list[dict[str, object]]
    mean_confidence: float | None
    cost_microusd: int
    cost_known: bool = True


@dataclass(frozen=True)
class WritingAssistResult:
    summary: str
    suggestions: list[dict[str, object]]
    confidence: float
    cost_microusd: int
    cost_known: bool = True


def _reported_cost(payload: dict[str, Any]) -> tuple[int, bool]:
    cost = payload.get("cost_microusd")
    if isinstance(cost, int) and not isinstance(cost, bool) and 0 <= cost <= 2_147_483_647:
        return cost, True
    return 0, False


def _post_json(
    url: str,
    body: bytes,
    *,
    content_type: str,
    token: str | None,
    timeout: int,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "Content-Type": content_type}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read(1_000_001))
    except (urllib.error.URLError, TimeoutError):
        raise ProviderFailure("provider_unavailable") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ProviderFailure("invalid_provider_response") from None
    if not isinstance(payload, dict):
        raise ProviderFailure("invalid_provider_response")
    return payload


def call_transcription_provider(
    url: str,
    audio: bytes,
    mime_type: str,
    *,
    token: str | None,
    timeout: int,
    idempotency_key: str | None = None,
) -> TranscriptionResult:
    payload = _post_json(
        url,
        audio,
        content_type=mime_type,
        token=token,
        timeout=timeout,
        extra_headers=(
            {"Idempotency-Key": idempotency_key} if idempotency_key is not None else None
        ),
    )
    text = payload.get("text")
    raw_words = payload.get("words")
    if not isinstance(text, str) or not text.strip() or not isinstance(raw_words, list):
        raise ProviderFailure("invalid_provider_response")
    words: list[dict[str, object]] = []
    for item in raw_words[:300]:
        if not isinstance(item, dict):
            raise ProviderFailure("invalid_provider_response")
        word = item.get("text")
        confidence = item.get("confidence")
        if not isinstance(word, str) or not isinstance(confidence, (int, float)):
            raise ProviderFailure("invalid_provider_response")
        try:
            words.append(
                {
                    "text": word[:100],
                    "start_ms": max(0, int(item.get("start_ms", 0))),
                    "end_ms": max(0, int(item.get("end_ms", 0))),
                    "confidence": max(0.0, min(1.0, float(confidence))),
                }
            )
        except (TypeError, ValueError):
            raise ProviderFailure("invalid_provider_response") from None
    if not words:
        raise ProviderFailure("invalid_provider_response")
    confidences = [item["confidence"] for item in words]
    mean = sum(value for value in confidences if isinstance(value, float)) / len(words)
    cost, cost_known = _reported_cost(payload)
    return TranscriptionResult(
        text=text.strip()[:5000],
        words=words,
        mean_confidence=round(mean, 4),
        cost_microusd=cost,
        cost_known=cost_known,
    )


def call_writing_provider(
    url: str,
    text: str,
    rubric: list[dict[str, object]],
    *,
    token: str | None,
    timeout: int,
    idempotency_key: str | None = None,
) -> WritingAssistResult:
    body = json.dumps({"text": text, "rubric": rubric}, ensure_ascii=False).encode()
    payload = _post_json(
        url,
        body,
        content_type="application/json",
        token=token,
        timeout=timeout,
        extra_headers={"Idempotency-Key": idempotency_key} if idempotency_key else None,
    )
    summary = payload.get("summary")
    raw_suggestions = payload.get("suggestions")
    confidence = payload.get("confidence")
    if (
        not isinstance(summary, str)
        or not isinstance(raw_suggestions, list)
        or not isinstance(confidence, (int, float))
    ):
        raise ProviderFailure("invalid_provider_response")
    suggestions: list[dict[str, object]] = []
    for item in raw_suggestions[:12]:
        if not isinstance(item, dict):
            continue
        criterion, message = item.get("criterion"), item.get("message")
        if isinstance(criterion, str) and isinstance(message, str):
            suggestions.append({"criterion": criterion[:100], "message": message[:500]})
    cost, cost_known = _reported_cost(payload)
    try:
        normalized_confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        raise ProviderFailure("invalid_provider_response") from None
    return WritingAssistResult(
        summary=summary.strip()[:1000],
        suggestions=suggestions,
        confidence=normalized_confidence,
        cost_microusd=cost,
        cost_known=cost_known,
    )


def call_ollama_writing_provider(
    base_url: str,
    model: str,
    text: str,
    rubric: list[dict[str, object]],
    *,
    timeout: int,
) -> WritingAssistResult:
    """Adapta a API nativa do Ollama ao contrato interno de escrita.

    O modelo roda localmente, recebe um schema JSON estrito e nunca ganha
    permissão para decidir nota, prontidão ou progresso. Esses valores
    continuam vindo da rubrica determinística da aplicação.
    """

    failed_checks = [
        item for item in rubric if item.get("passed") is False and isinstance(item.get("code"), str)
    ]
    failed_codes = [str(item["code"]) for item in failed_checks]
    if not failed_codes:
        return WritingAssistResult(
            summary="Seu texto atende aos critérios objetivos desta atividade.",
            suggestions=[],
            confidence=1.0,
            cost_microusd=0,
        )

    output_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "suggestions": {
                "type": "array",
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "properties": {
                        "criterion": {"type": "string", "enum": failed_codes},
                        "message": {"type": "string"},
                    },
                    "required": ["criterion", "message"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["summary", "suggestions"],
        "additionalProperties": False,
    }
    prompt = json.dumps(
        {
            "task": (
                "Give concise, supportive feedback in Portuguese to a Brazilian learner of "
                "English. Comment only on failed_checks. Use the exact check code in criterion. "
                "Do not discuss checks that passed, infer grammar errors, introduce new criteria, "
                "assign a grade, provide a rewritten answer, or repeat the student text. Base each "
                "message only on the corresponding label and suggestion supplied by the app."
            ),
            "student_text": text,
            "failed_checks": failed_checks,
            "output_schema": output_schema,
        },
        ensure_ascii=False,
    )
    body = json.dumps(
        {
            "model": model,
            "stream": False,
            "format": output_schema,
            "options": {"temperature": 0},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an English writing tutor. Return only JSON matching the schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        },
        ensure_ascii=False,
    ).encode()
    payload = _post_json(
        f"{base_url.rstrip('/')}/api/chat",
        body,
        content_type="application/json",
        token=None,
        timeout=timeout,
    )
    message = payload.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ProviderFailure("invalid_provider_response")
    try:
        generated = json.loads(message["content"])
    except (json.JSONDecodeError, TypeError):
        raise ProviderFailure("invalid_provider_response") from None
    if not isinstance(generated, dict):
        raise ProviderFailure("invalid_provider_response")
    summary = generated.get("summary")
    raw_suggestions = generated.get("suggestions")
    if not isinstance(summary, str) or not summary.strip() or not isinstance(raw_suggestions, list):
        raise ProviderFailure("invalid_provider_response")
    suggestions: list[dict[str, object]] = []
    for item in raw_suggestions[:8]:
        if not isinstance(item, dict):
            raise ProviderFailure("invalid_provider_response")
        criterion, message_text = item.get("criterion"), item.get("message")
        if not isinstance(criterion, str) or not isinstance(message_text, str):
            raise ProviderFailure("invalid_provider_response")
        normalized_criterion = criterion.strip()
        normalized_message = message_text.strip()
        # Schema estruturado ajuda o modelo, mas a fronteira de confiança é
        # aplicada novamente no servidor. Qualquer critério inventado ou
        # previamente aprovado é silenciosamente descartado.
        if normalized_criterion not in failed_codes or not normalized_message:
            continue
        suggestions.append(
            {"criterion": normalized_criterion[:100], "message": normalized_message[:500]}
        )
    return WritingAssistResult(
        summary=summary.strip()[:1000],
        suggestions=suggestions,
        # Ollama não fornece probabilidade calibrada para esta resposta. O
        # valor conservador mantém o aviso de baixa confiança visível.
        confidence=0.5,
        cost_microusd=0,
    )


@dataclass(frozen=True)
class DialogueResult:
    """Resposta crua do provedor de diálogo, antes do saneamento.

    `raw` vai inteiro para `dialogue_prompts.sanitize_provider_output`, que é
    quem decide se a resposta é utilizável: aqui só se garante que houve uma
    resposta JSON e se mede o custo. A separação é de propósito — este módulo
    fala HTTP, o outro conhece o contrato do turno.
    """

    raw: object
    cost_microusd: int
    cost_known: bool


def _cloudflare_chat(payload: dict[str, Any]) -> object:
    """`result.response` vem como objeto (json_schema) ou string JSON."""
    result = payload.get("result")
    if not isinstance(result, dict):
        return payload
    response = result.get("response")
    if isinstance(response, str):
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            raise ProviderFailure("invalid_provider_response") from None
    return response


def call_dialogue_provider(
    url: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    token: str | None,
    timeout: int,
    idempotency_key: str | None = None,
) -> DialogueResult:
    """Um turno do parceiro, com a resposta restrita pelo JSON Schema.

    O corpo é o mesmo medido no spike do IA-45 contra o Workers AI
    (`messages` + `response_format` json_schema + `temperature: 0`), e
    `temperature` zero é o que torna o turno reproduzível para o gate humano.
    Um gateway próprio que aceite o mesmo corpo serve sem mudança aqui.
    """
    body = json.dumps(
        {
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": schema},
            "temperature": 0,
            "max_tokens": 200,
        },
        ensure_ascii=False,
    ).encode()
    payload = _post_json(
        url,
        body,
        content_type="application/json",
        token=token,
        timeout=timeout,
        extra_headers={"Idempotency-Key": idempotency_key} if idempotency_key else None,
    )
    cost, cost_known = _reported_cost(payload)
    return DialogueResult(raw=_cloudflare_chat(payload), cost_microusd=cost, cost_known=cost_known)


def call_ollama_dialogue_provider(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    timeout: int,
) -> DialogueResult:
    """Mesmo turno, por Ollama local. Só desenvolvimento.

    A VM pública é compartilhada e sem GPU (ADR), então este caminho existe
    para iterar no prompt sem gastar cota — e nunca reporta custo, porque não
    há nenhum a reportar.
    """
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0},
        },
        ensure_ascii=False,
    ).encode()
    payload = _post_json(
        f"{base_url.rstrip('/')}/api/chat",
        body,
        content_type="application/json",
        token=None,
        timeout=timeout,
    )
    message = payload.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ProviderFailure("invalid_provider_response")
    try:
        raw: object = json.loads(content)
    except json.JSONDecodeError:
        raise ProviderFailure("invalid_provider_response") from None
    return DialogueResult(raw=raw, cost_microusd=0, cost_known=True)


def compare_transcript(expected: str, actual: str) -> float:
    def normalized(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+(?:'[a-z]+)?", value.lower().replace("’", "'")))

    return round(SequenceMatcher(None, normalized(expected), normalized(actual)).ratio(), 4)
