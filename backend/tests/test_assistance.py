"""Contrato estreito do gateway assistido e comparação determinística."""

import json
import urllib.error
import urllib.request

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


def test_ollama_usa_schema_estrito_e_confiança_conservadora(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def respond(request: urllib.request.Request, **_kwargs: object) -> FakeResponse:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data or b"{}")
        return FakeResponse(
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "summary": "A comparação está clara.",
                            "suggestions": [
                                {
                                    "criterion": "comparison",
                                    "message": "Acrescente uma razão para sua escolha.",
                                }
                            ],
                        }
                    ),
                },
                "done": True,
            }
        )

    monkeypatch.setattr(assistance.urllib.request, "urlopen", respond)
    result = assistance.call_ollama_writing_provider(
        "http://host.docker.internal:11434/",
        "qwen2.5:7b",
        "The taxi is faster.",
        [
            {
                "code": "comparison",
                "label": "Use uma comparação",
                "passed": False,
                "suggestion": "Inclua uma comparação.",
            }
        ],
        timeout=20,
    )

    assert captured["url"] == "http://host.docker.internal:11434/api/chat"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen2.5:7b"
    assert body["stream"] is False
    assert isinstance(body["format"], dict)
    assert body["format"]["properties"]["suggestions"]["items"]["properties"][
        "criterion"
    ]["enum"] == ["comparison"]
    assert body["options"] == {"temperature": 0}
    assert result.summary == "A comparação está clara."
    assert result.confidence == 0.5
    assert result.cost_microusd == 0


def test_ollama_descarta_criterio_inventado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        assistance.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "summary": "Revise o tamanho do texto.",
                            "suggestions": [
                                {"criterion": "grammar", "message": "Troque is por are."},
                                {
                                    "criterion": "word_count",
                                    "message": "Acrescente mais detalhes à sua resposta.",
                                },
                            ],
                        }
                    ),
                }
            }
        ),
    )

    result = assistance.call_ollama_writing_provider(
        "http://localhost:11434",
        "qwen2.5:7b",
        "The taxi is faster.",
        [
            {
                "code": "word_count",
                "label": "Pelo menos 35 palavras",
                "passed": False,
                "suggestion": "Acrescente detalhes até chegar a 35 palavras.",
            },
            {
                "code": "comparison",
                "label": "Use uma comparação",
                "passed": True,
                "suggestion": "Inclua uma comparação.",
            },
        ],
        timeout=20,
    )

    assert result.suggestions == [
        {
            "criterion": "word_count",
            "message": "Acrescente mais detalhes à sua resposta.",
        }
    ]


def test_ollama_nao_e_chamado_quando_todos_os_criterios_passam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_call(*args: object, **kwargs: object) -> FakeResponse:
        raise AssertionError("Ollama não deveria ser chamado")

    monkeypatch.setattr(assistance.urllib.request, "urlopen", unexpected_call)
    result = assistance.call_ollama_writing_provider(
        "http://localhost:11434",
        "qwen2.5:7b",
        "The taxi is faster than the bus.",
        [{"code": "comparison", "passed": True}],
        timeout=20,
    )

    assert result.suggestions == []
    assert result.confidence == 1.0


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
