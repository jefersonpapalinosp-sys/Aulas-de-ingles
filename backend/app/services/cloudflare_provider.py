"""Adaptador HTTPS direto para Workers AI, sem proxy extra nem retenção própria.

Sem redirects, retries, cache ou IDs de aluno enviados ao fornecedor. Falhas
nunca incluem corpo/URL/token. Confiança STT ausente permanece desconhecida.
"""

import json
import math
import re
import urllib.error
import urllib.request
from typing import Any, TypeGuard

from app.services.assistance import DialogueResult, ProviderFailure, TranscriptionResult

MODELS = {
    "dialogue": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "transcription": "@cf/openai/whisper-tiny-en",
}
PREFIX = "https://api.cloudflare.com/client/v4/accounts/"


def validate_url(url: str, modality: str) -> None:
    model = MODELS.get(modality)
    if model is None or not re.fullmatch(
        re.escape(PREFIX) + r"[a-f0-9]{32}/ai/run/" + re.escape(model), url
    ):
        raise RuntimeError("URL Cloudflare deve usar a conta e o modelo fixo do piloto via HTTPS.")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _request(url: str, body: bytes, token: str | None, timeout: int) -> dict[str, Any]:
    if not token or len(body) > 2_000_000:
        raise ProviderFailure("provider_unavailable")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    # A URL de STT recebe bytes, como prescrito pelo modelo Whisper Tiny.
    if url.endswith(MODELS["transcription"]):
        request.add_header("Content-Type", "application/octet-stream")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ProviderFailure("invalid_provider_response")
        payload = json.loads(raw)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderFailure("provider_unavailable") from None
    except (ValueError, UnicodeDecodeError):
        raise ProviderFailure("invalid_provider_response") from None
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ProviderFailure("invalid_provider_response")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ProviderFailure("invalid_provider_response")
    return result


def _free_plan() -> bool:
    from app.core.config import get_settings

    # Zero só quando a operação confirmou Workers Free; nunca estimar uma fatura
    # a partir de tokens/Neurons ou transformar custo ausente em zero conhecido.
    return get_settings().assist_cloudflare_free_plan_confirmed


def dialogue(
    url: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    token: str | None,
    timeout: int,
    idempotency_key: str | None = None,
) -> DialogueResult:
    validate_url(url, "dialogue")
    result = _request(
        url,
        json.dumps(
            {
                "messages": messages,
                "response_format": {"type": "json_schema", "json_schema": schema},
                "temperature": 0,
                "max_tokens": 200,
            },
            ensure_ascii=False,
        ).encode(),
        token,
        timeout,
    )
    raw = result.get("response")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise ProviderFailure("invalid_provider_response") from None
    if not isinstance(raw, dict):
        raise ProviderFailure("invalid_provider_response")
    return DialogueResult(raw=raw, cost_microusd=0, cost_known=_free_plan())


def _number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def transcribe(
    url: str,
    audio: bytes,
    mime_type: str,
    *,
    token: str | None,
    timeout: int,
    idempotency_key: str | None = None,
) -> TranscriptionResult:
    validate_url(url, "transcription")
    result = _request(url, audio, token, timeout)
    text = result.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 5000:
        raise ProviderFailure("invalid_provider_response")
    raw_words = result.get("words", [])
    if not isinstance(raw_words, list) or len(raw_words) > 300:
        raise ProviderFailure("invalid_provider_response")
    words: list[dict[str, object]] = []
    confidences: list[float] = []
    for item in raw_words:
        if not isinstance(item, dict):
            raise ProviderFailure("invalid_provider_response")
        word = item.get("word", item.get("text"))
        # Whisper Tiny inclui um marcador vazio inicial (0, 0), sem fala.
        if isinstance(word, str) and not word.strip():
            continue
        start, end, confidence = item.get("start"), item.get("end"), item.get("confidence")
        if (
            not isinstance(word, str)
            or not word.strip()
            or not _number(start)
            or not _number(end)
            or not 0 <= start <= end <= 30
            or (confidence is not None and (not _number(confidence) or not 0 <= confidence <= 1))
        ):
            raise ProviderFailure("invalid_provider_response")
        words.append(
            {
                "text": word[:100],
                "start_ms": round(start * 1000),
                "end_ms": round(end * 1000),
                "confidence": confidence,
            }
        )
        if confidence is not None:
            confidences.append(float(confidence))
    mean = sum(confidences) / len(words) if words and len(confidences) == len(words) else None
    return TranscriptionResult(text.strip(), words, mean, 0, cost_known=_free_plan())
