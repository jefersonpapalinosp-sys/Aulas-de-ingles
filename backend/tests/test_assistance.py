"""Contrato estreito do gateway assistido e comparação determinística."""

import json
import urllib.error

import pytest

from app.services import assistance


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.payload


def test_gateway_normaliza_transcricao_e_calcula_semelhanca(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        assistance.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(
            {
                "text": "A taxi is faster than a bus",
                "words": [
                    {"text": "taxi", "start_ms": 0, "end_ms": 100, "confidence": 1.2},
                    {"text": "bus", "start_ms": 101, "end_ms": 200, "confidence": 0.6},
                ],
                "cost_microusd": 90,
            }
        ),
    )
    result = assistance.call_transcription_provider(
        "https://provider.test/stt",
        b"audio",
        "audio/webm",
        token="secret",
        timeout=2,
    )
    assert result.mean_confidence == 0.8
    assert result.words[0]["confidence"] == 1.0
    assert result.cost_microusd == 90
    assert assistance.compare_transcript("A taxi is faster than a bus.", result.text) == 1.0


def test_gateway_valida_feedback_de_escrita(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        assistance.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(
            {
                "summary": "Clear comparison.",
                "suggestions": [{"criterion": "detail", "message": "Add one reason."}],
                "confidence": 0.84,
                "cost_microusd": 120,
            }
        ),
    )
    result = assistance.call_writing_provider(
        "https://provider.test/writing",
        "The taxi is faster.",
        [{"code": "comparison"}],
        token=None,
        timeout=2,
    )
    assert result.summary == "Clear comparison."
    assert result.suggestions[0]["criterion"] == "detail"
    assert result.confidence == 0.84


def test_gateway_converte_rede_e_json_invalido_em_codigo_tecnico(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        assistance.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with pytest.raises(assistance.ProviderFailure, match="provider_unavailable"):
        assistance.call_transcription_provider(
            "https://provider.test/stt",
            b"audio",
            "audio/webm",
            token=None,
            timeout=2,
        )
