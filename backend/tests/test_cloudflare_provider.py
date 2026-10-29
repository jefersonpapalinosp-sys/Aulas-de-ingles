"""Contrato Workers AI: segredo, origem fixa, dados incertos e custo Free."""

import io
import json
import urllib.error
import urllib.request

import pytest

from app.core.config import Settings, get_settings
from app.services import cloudflare_provider as cf
from app.services.assistance import ProviderFailure

URL = cf.PREFIX + "a" * 32 + "/ai/run/"


@pytest.mark.parametrize(
    "bad",
    [
        "http://api.cloudflare.com/",
        "https://evil.test/",
        URL + cf.MODELS["dialogue"] + "?x=1",
        URL + cf.MODELS["dialogue"] + "/",
    ],
)
def test_only_fixed_https_models_allowed(bad):
    with pytest.raises(RuntimeError):
        cf.validate_url(bad, "dialogue")


def test_request_sends_only_provider_token_and_never_forwards_ids(monkeypatch):
    seen = []

    class Opener:
        def open(self, request, timeout):
            seen.append(request)
            return io.BytesIO(
                json.dumps(
                    {
                        "success": True,
                        "result": {"response": {"partner_text": "Hello", "hints": []}},
                    }
                ).encode()
            )

    monkeypatch.setattr(urllib.request, "build_opener", lambda handler: Opener())
    monkeypatch.setattr(get_settings(), "assist_cloudflare_free_plan_confirmed", False)
    result = cf.dialogue(
        URL + cf.MODELS["dialogue"],
        [{"role": "user", "content": "Hello"}],
        {},
        token="private-test-token",
        timeout=1,
        idempotency_key="private-turn-id",
    )
    assert result.cost_known is False
    request = seen[0]
    assert request.get_header("Authorization") == "Bearer private-test-token"
    assert b"private-turn-id" not in request.data
    assert request.get_header("Idempotency-key") is None
    assert json.loads(request.data)["max_tokens"] == 200


def test_redirect_cannot_forward_token():
    request = urllib.request.Request(URL + cf.MODELS["dialogue"])
    assert cf.NoRedirect().redirect_request(request, None, 302, "", {}, "https://evil.test") is None


@pytest.mark.parametrize(
    "payload",
    [
        b"bad json",
        b'{"success":false,"errors":[{"message":"secret"}]}',
        b'{"success":true,"result":[]}',
        b"x" * 1_000_001,
    ],
)
def test_bad_responses_never_leak_body(monkeypatch, payload):
    class Opener:
        def open(self, *args, **kwargs):
            return io.BytesIO(payload)

    monkeypatch.setattr(urllib.request, "build_opener", lambda handler: Opener())
    with pytest.raises(ProviderFailure, match="^invalid_provider_response$"):
        cf.transcribe(
            URL + cf.MODELS["transcription"], b"audio", "audio/wav", token="token", timeout=1
        )


def test_http_error_never_leaks_token_or_body(monkeypatch):
    class Opener:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError("https://secret", 403, "private-token", {}, None)

    monkeypatch.setattr(urllib.request, "build_opener", lambda handler: Opener())
    with pytest.raises(ProviderFailure, match="^provider_unavailable$"):
        cf.transcribe(
            URL + cf.MODELS["transcription"], b"audio", "audio/wav", token="token", timeout=1
        )


def test_whisper_missing_confidence_is_unknown_not_zero(monkeypatch):
    monkeypatch.setattr(
        cf,
        "_request",
        lambda *args: {"text": "A bus.", "words": [{"word": "bus", "start": 0.1, "end": 0.8}]},
    )
    monkeypatch.setattr(get_settings(), "assist_cloudflare_free_plan_confirmed", True)
    result = cf.transcribe(
        URL + cf.MODELS["transcription"], b"audio", "audio/wav", token="token", timeout=1
    )
    assert result.words == [{"text": "bus", "start_ms": 100, "end_ms": 800, "confidence": None}]
    assert result.mean_confidence is None
    assert result.cost_known and result.cost_microusd == 0


def test_whisper_without_timing_keeps_text_without_inventing_words(monkeypatch):
    monkeypatch.setattr(cf, "_request", lambda *args: {"text": "A bus."})
    result = cf.transcribe(
        URL + cf.MODELS["transcription"], b"audio", "audio/wav", token="token", timeout=1
    )
    assert result.text == "A bus." and result.words == [] and result.mean_confidence is None


@pytest.mark.parametrize(
    "word",
    [
        {"word": "bus", "start": -1, "end": 1},
        {"word": "bus", "start": 0, "end": float("nan")},
        {"word": "bus", "start": 0, "end": 1, "confidence": True},
    ],
)
def test_invalid_word_metadata_fails_closed(monkeypatch, word):
    monkeypatch.setattr(cf, "_request", lambda *args: {"text": "bus", "words": [word]})
    with pytest.raises(ProviderFailure):
        cf.transcribe(
            URL + cf.MODELS["transcription"], b"audio", "audio/wav", token="token", timeout=1
        )


def test_cloudflare_requires_explicit_free_plan_and_no_automatic_retries():
    settings = Settings(
        app_env="dev", assist_provider_kind="cloudflare", assisted_features_enabled=True
    )
    with pytest.raises(RuntimeError, match="plano Free"):
        settings.validar()
    settings.assist_cloudflare_free_plan_confirmed = True
    with pytest.raises(RuntimeError, match="uma tentativa"):
        settings.validar()
    settings.assist_job_max_attempts = 1
    settings.validar()
    settings.assist_writing_url = "https://invalid.test/writing"
    with pytest.raises(RuntimeError, match="escrita"):
        settings.validar()


def test_whisper_empty_start_marker_is_not_a_word(monkeypatch):
    monkeypatch.setattr(
        cf,
        "_request",
        lambda *args: {
            "text": "bus",
            "words": [
                {"word": "", "start": 0, "end": 0},
                {"word": "bus", "start": 0.1, "end": 1.0},
            ],
        },
    )
    result = cf.transcribe(
        URL + cf.MODELS["transcription"], b"audio", "audio/wav", token="token", timeout=1
    )
    assert len(result.words) == 1 and result.words[0]["text"] == "bus"
