"""Consentimento, persistência e isolamento das gravações de speaking."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import TranscriptionJob
from app.services import assistance, transcription_queue


async def conta(client: AsyncClient, sufixo: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"speaking-{sufixo}@exemplo.com",
            "password": "senha-bem-grande",
            "display_name": sufixo,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def cue_id(client: AsyncClient) -> int:
    lesson = (await client.get("/api/lessons/31")).json()
    return lesson["media"][0]["cues"][0]["id"]


@pytest.mark.asyncio
async def test_gravacoes_exigem_login_e_consentimento(client: AsyncClient) -> None:
    cue = await cue_id(client)
    body = {"cue_id": cue, "duration_ms": 1200, "self_rating": "almost", "consent": True}

    assert (await client.get("/api/speaking/attempts")).status_code == 401
    assert (await client.post("/api/speaking/attempts", json=body)).status_code == 401

    headers = await conta(client, "consentimento")
    sem_consentimento = await client.post(
        "/api/speaking/attempts", headers=headers, json={**body, "consent": False}
    )
    longa = await client.post(
        "/api/speaking/attempts", headers=headers, json={**body, "duration_ms": 30_001}
    )
    assert sem_consentimento.status_code == 422
    assert longa.status_code == 422


@pytest.mark.asyncio
async def test_fluxo_de_upload_listagem_audio_e_exclusao(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers = await conta(client, "dona")
    cue = await cue_id(client)

    created = await client.post(
        "/api/speaking/attempts",
        headers=headers,
        json={
            "cue_id": cue,
            "duration_ms": 1700,
            "self_rating": "confident",
            "consent": True,
        },
    )
    assert created.status_code == 201
    attempt = created.json()
    assert attempt["status"] == "pending"
    assert (await client.get("/api/speaking/attempts?lesson=31", headers=headers)).json() == []

    audio = b"fake-webm-audio"
    uploaded = await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm;codecs=opus"},
        content=audio,
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "ready"
    assert uploaded.json()["file_size"] == len(audio)
    assert len(list(tmp_path.iterdir())) == 1

    listed = (await client.get("/api/speaking/attempts?lesson=31", headers=headers)).json()
    assert [item["id"] for item in listed] == [attempt["id"]]
    downloaded = await client.get(f"/api/speaking/attempts/{attempt['id']}/audio", headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == audio
    assert downloaded.headers["content-type"].startswith("audio/webm")

    outra_conta = await conta(client, "intrusa")
    for method, suffix in (("get", "/audio"), ("delete", "")):
        response = await getattr(client, method)(
            f"/api/speaking/attempts/{attempt['id']}{suffix}", headers=outra_conta
        )
        assert response.status_code == 404
    assert (await client.get("/api/speaking/attempts", headers=outra_conta)).json() == []

    deleted = await client.delete(f"/api/speaking/attempts/{attempt['id']}", headers=headers)
    assert deleted.status_code == 204
    assert list(tmp_path.iterdir()) == []
    assert (
        await client.get(f"/api/speaking/attempts/{attempt['id']}/audio", headers=headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_upload_valida_formato_tamanho_e_envio_unico(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "speaking_max_bytes", 8)
    headers = await conta(client, "limites")
    body = {
        "cue_id": await cue_id(client),
        "duration_ms": 900,
        "self_rating": None,
        "consent": True,
    }

    attempt_id = (await client.post("/api/speaking/attempts", headers=headers, json=body)).json()[
        "id"
    ]
    invalid = await client.put(
        f"/api/speaking/attempts/{attempt_id}/audio",
        headers={**headers, "Content-Type": "text/plain"},
        content=b"voice",
    )
    oversized = await client.put(
        f"/api/speaking/attempts/{attempt_id}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=b"123456789",
    )
    assert invalid.status_code == 415
    assert oversized.status_code == 413

    accepted = await client.put(
        f"/api/speaking/attempts/{attempt_id}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=b"voice",
    )
    repeated = await client.put(
        f"/api/speaking/attempts/{attempt_id}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=b"again",
    )
    assert accepted.status_code == 200
    assert repeated.status_code == 409
    speaking_review = (
        await client.get("/api/review/due?item_type=speaking_prompt", headers=headers)
    ).json()
    assert len(speaking_review) == 1
    assert speaking_review[0]["media_url"]
    assert speaking_review[0]["skill"] == "speaking"
    await client.delete(f"/api/speaking/attempts/{attempt_id}", headers=headers)


@pytest.mark.asyncio
async def test_transcricao_assistida_expoe_confianca_comparacao_custo_e_avaliacao(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.test/stt")
    monkeypatch.setattr(settings, "assist_provider_name", "provider-test")
    monkeypatch.setattr(settings, "assist_daily_quota", 3)
    monkeypatch.setattr(settings, "assist_retention_days", 7)
    monkeypatch.setattr(
        assistance,
        "call_transcription_provider",
        lambda *args, **kwargs: assistance.TranscriptionResult(
            text="Don't take the bus. A taxi is faster than a boss.",
            words=[
                {"text": "Don't", "start_ms": 0, "end_ms": 200, "confidence": 0.94},
                {"text": "boss", "start_ms": 201, "end_ms": 450, "confidence": 0.42},
            ],
            mean_confidence=0.68,
            cost_microusd=1250,
        ),
    )
    headers = await conta(client, "transcricao")
    cue = await cue_id(client)
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={
                "cue_id": cue,
                "duration_ms": 1200,
                "self_rating": "almost",
                "consent": True,
            },
        )
    ).json()
    await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=b"voice-for-provider",
    )

    requested = await client.post(
        f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers
    )
    assert requested.status_code == 202
    assert requested.json()["status"] == "queued"
    assert requested.json()["attempt_count"] == 0
    assert await transcription_queue.process_next_transcription() is True
    listed = (await client.get("/api/speaking/attempts?lesson=31", headers=headers)).json()
    transcription = listed[0]["transcription"]
    assert transcription["status"] == "completed"
    assert transcription["automated"] is True
    assert transcription["evaluation_only"] is True
    assert transcription["low_confidence"] is True
    assert transcription["mean_confidence"] == 0.68
    assert transcription["similarity_score"] < 1
    assert transcription["words"][1]["confidence"] == 0.42
    assert transcription["cost_microusd"] == 1250

    usage = (await client.get("/api/assist/status", headers=headers)).json()
    assert usage["used_today"] == 1
    assert usage["remaining_today"] == 2
    assert usage["cost_microusd_today"] == 1250
    rated = await client.put(
        f"/api/speaking/transcriptions/{transcription['id']}/rating",
        headers=headers,
        json={"rating": "not_helpful"},
    )
    assert rated.json()["human_rating"] == "not_helpful"
    assert (
        await client.delete(f"/api/speaking/transcriptions/{transcription['id']}", headers=headers)
    ).status_code == 204
    assert (await client.get("/api/speaking/attempts", headers=headers)).json()[0][
        "transcription"
    ] is None


@pytest.mark.asyncio
async def test_falha_do_provedor_mantem_audio_e_autoavaliacao(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.test/stt")
    monkeypatch.setattr(settings, "assist_job_max_attempts", 1)

    def fail(*args: object, **kwargs: object) -> assistance.TranscriptionResult:
        raise assistance.ProviderFailure("provider_unavailable")

    monkeypatch.setattr(assistance, "call_transcription_provider", fail)
    headers = await conta(client, "falha-provider")
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={
                "cue_id": await cue_id(client),
                "duration_ms": 900,
                "self_rating": "repeat",
                "consent": True,
            },
        )
    ).json()
    await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=b"voice",
    )
    await client.post(f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers)
    assert await transcription_queue.process_next_transcription() is True
    item = (await client.get("/api/speaking/attempts", headers=headers)).json()[0]
    assert item["transcription"]["status"] == "failed"
    assert item["transcription"]["error_code"] == "provider_unavailable"
    assert (
        await client.get(f"/api/speaking/attempts/{attempt['id']}/audio", headers=headers)
    ).content == b"voice"


@pytest.mark.asyncio
async def test_worker_repete_com_backoff_e_chave_idempotente(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.test/stt")
    monkeypatch.setattr(settings, "assist_job_max_attempts", 3)
    monkeypatch.setattr(settings, "assist_job_retry_base_seconds", 0)
    keys: list[str | None] = []

    def flaky(*args: object, **kwargs: object) -> assistance.TranscriptionResult:
        keys.append(kwargs.get("idempotency_key"))  # type: ignore[arg-type]
        if len(keys) == 1:
            raise assistance.ProviderFailure("provider_unavailable")
        return assistance.TranscriptionResult(
            text="A taxi is faster than a bus.",
            words=[{"text": "taxi", "start_ms": 0, "end_ms": 200, "confidence": 0.9}],
            mean_confidence=0.9,
            cost_microusd=10,
        )

    monkeypatch.setattr(assistance, "call_transcription_provider", flaky)
    headers = await conta(client, "retry-worker")
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={
                "cue_id": await cue_id(client),
                "duration_ms": 900,
                "self_rating": "almost",
                "consent": True,
            },
        )
    ).json()
    await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=b"voice",
    )
    requested = (
        await client.post(
            f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers
        )
    ).json()

    assert await transcription_queue.process_next_transcription() is True
    after_failure = (await client.get("/api/speaking/attempts", headers=headers)).json()[0][
        "transcription"
    ]
    assert after_failure["status"] == "queued"
    assert after_failure["attempt_count"] == 1
    assert after_failure["error_code"] == "provider_unavailable"

    assert await transcription_queue.process_next_transcription() is True
    completed = (await client.get("/api/speaking/attempts", headers=headers)).json()[0][
        "transcription"
    ]
    assert completed["status"] == "completed"
    assert completed["attempt_count"] == 2
    assert keys == [keys[0], keys[0]]
    assert isinstance(keys[0], str)
    assert requested["max_attempts"] == 3


@pytest.mark.asyncio
async def test_workers_concorrentes_reivindicam_job_uma_unica_vez(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.test/stt")
    calls = 0

    def transcribe(*args: object, **kwargs: object) -> assistance.TranscriptionResult:
        nonlocal calls
        calls += 1
        return assistance.TranscriptionResult(
            text="A taxi is faster.",
            words=[{"text": "taxi", "start_ms": 0, "end_ms": 100, "confidence": 0.9}],
            mean_confidence=0.9,
            cost_microusd=0,
        )

    monkeypatch.setattr(assistance, "call_transcription_provider", transcribe)
    headers = await conta(client, "workers-concorrentes")
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={
                "cue_id": await cue_id(client),
                "duration_ms": 900,
                "self_rating": "almost",
                "consent": True,
            },
        )
    ).json()
    await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=b"voice",
    )
    await client.post(f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers)

    results = await asyncio.gather(
        transcription_queue.process_next_transcription(),
        transcription_queue.process_next_transcription(),
    )

    assert sorted(results) == [False, True]
    assert calls == 1


@pytest.mark.asyncio
async def test_worker_retoma_job_interrompido_apos_timeout(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.test/stt")
    monkeypatch.setattr(
        assistance,
        "call_transcription_provider",
        lambda *args, **kwargs: assistance.TranscriptionResult(
            text="A taxi is faster.",
            words=[{"text": "taxi", "start_ms": 0, "end_ms": 100, "confidence": 0.9}],
            mean_confidence=0.9,
            cost_microusd=0,
        ),
    )
    headers = await conta(client, "retomada-worker")
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={
                "cue_id": await cue_id(client),
                "duration_ms": 900,
                "self_rating": "almost",
                "consent": True,
            },
        )
    ).json()
    await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=b"voice",
    )
    requested = (
        await client.post(
            f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers
        )
    ).json()
    job = await session.get(TranscriptionJob, requested["id"])
    assert job is not None
    job.status = "processing"
    job.attempt_count = 1
    job.processing_started_at = datetime.now(UTC) - timedelta(
        seconds=settings.assist_job_stale_seconds + 1
    )
    await session.commit()

    assert await transcription_queue.process_next_transcription() is True
    resumed = (await client.get("/api/speaking/attempts", headers=headers)).json()[0][
        "transcription"
    ]
    assert resumed["status"] == "completed"
    assert resumed["attempt_count"] == 2
