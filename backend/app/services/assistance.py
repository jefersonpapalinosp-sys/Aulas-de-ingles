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
    mean_confidence: float
    cost_microusd: int


@dataclass(frozen=True)
class WritingAssistResult:
    summary: str
    suggestions: list[dict[str, object]]
    confidence: float
    cost_microusd: int


def _post_json(
    url: str,
    body: bytes,
    *,
    content_type: str,
    token: str | None,
    timeout: int,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "Content-Type": content_type}
    if token:
        headers["Authorization"] = f"Bearer {token}"
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
) -> TranscriptionResult:
    payload = _post_json(
        url,
        audio,
        content_type=mime_type,
        token=token,
        timeout=timeout,
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
    cost = payload.get("cost_microusd", 0)
    return TranscriptionResult(
        text=text.strip()[:5000],
        words=words,
        mean_confidence=round(mean, 4),
        cost_microusd=max(0, int(cost)) if isinstance(cost, (int, float)) else 0,
    )


def call_writing_provider(
    url: str,
    text: str,
    rubric: list[dict[str, object]],
    *,
    token: str | None,
    timeout: int,
) -> WritingAssistResult:
    body = json.dumps({"text": text, "rubric": rubric}, ensure_ascii=False).encode()
    payload = _post_json(url, body, content_type="application/json", token=token, timeout=timeout)
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
    cost = payload.get("cost_microusd", 0)
    try:
        normalized_confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        raise ProviderFailure("invalid_provider_response") from None
    return WritingAssistResult(
        summary=summary.strip()[:1000],
        suggestions=suggestions,
        confidence=normalized_confidence,
        cost_microusd=max(0, int(cost)) if isinstance(cost, (int, float)) else 0,
    )


def compare_transcript(expected: str, actual: str) -> float:
    def normalized(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+(?:'[a-z]+)?", value.lower().replace("’", "'")))

    return round(SequenceMatcher(None, normalized(expected), normalized(actual)).ratio(), 4)
