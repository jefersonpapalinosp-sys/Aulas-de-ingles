"""Consentimento, persistência e isolamento das gravações de speaking."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import speaking as speaking_api
from app.core.config import get_settings
from app.db.models import (
    SkillEvidence,
    SpeakingAttempt,
    TranscriptCue,
    TranscriptionJob,
    User,
)
from app.performance import BYTES_HEADER, POOL_HEADER, SQL_HEADER
from app.services import assistance, transcription_queue
from tests.audio_samples import encoded


@pytest.fixture(autouse=True)
def speaking_history_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "editorial_snapshots_enabled", True)


@pytest.mark.asyncio
async def test_policy_reports_effective_limit_without_claiming_content_validation(
    client, monkeypatch
):
    monkeypatch.setattr(get_settings(), "speaking_max_bytes", 1500)
    result = await client.get("/api/speaking/policy")
    assert result.status_code == 200
    assert "no-store" in result.headers["cache-control"]
    assert result.json()["max_bytes"] == 1500
    assert result.json()["max_duration_ms"] == 30_000
    assert result.json()["content_validation"] == "decoded_audio_v1"


@pytest.mark.asyncio
async def test_concurrent_upload_same_body_is_idempotent_and_different_body_conflicts(
    client, session, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers = await conta(client, "upload-concurrent")
    body = {
        "cue_id": await cue_id(client),
        "duration_ms": 900,
        "self_rating": "confident",
        "consent": True,
    }
    attempt = (await client.post("/api/speaking/attempts", headers=headers, json=body)).json()
    url = f"/api/speaking/attempts/{attempt['id']}/audio"

    async def send(data):
        return await client.put(
            url, headers={**headers, "Content-Type": "audio/webm"}, content=data
        )

    first, second = await asyncio.gather(send(encoded()), send(encoded()))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert (await send(encoded(milliseconds=500))).status_code == 409
    assert len(list(tmp_path.iterdir())) == 1
    assert (
        await session.scalar(
            select(func.count())
            .select_from(SkillEvidence)
            .where(
                SkillEvidence.source_type == "speaking_attempt",
                SkillEvidence.source_id == attempt["id"],
            )
        )
        == 1
    )
    downloaded = await client.get(url, headers=headers)
    assert downloaded.content == encoded()


@pytest.mark.asyncio
async def test_chunked_body_checked_and_connection_released_during_receive(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "speaking_max_bytes", 8)
    headers = await conta(client, "chunked")
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={
                "cue_id": await cue_id(client),
                "duration_ms": 1000,
                "consent": True,
            },
        )
    ).json()
    from sqlalchemy.pool import AsyncAdaptedQueuePool

    from app.db.session import get_engine

    async def chunks():
        pool = get_engine().pool
        assert isinstance(pool, AsyncAdaptedQueuePool)
        assert pool.checkedout() == 0
        yield b"1234"
        yield b"56789"
        pytest.fail("Não deve consumir o restante depois de exceder o limite")

    response = await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=chunks(),
    )
    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_delete_during_upload_does_not_create_orphan(client, session, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers = await conta(client, "delete-upload")
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={
                "cue_id": await cue_id(client),
                "duration_ms": 1000,
                "consent": True,
            },
        )
    ).json()
    url = f"/api/speaking/attempts/{attempt['id']}"

    async def chunks():
        assert (await client.delete(url, headers=headers)).status_code == 204
        yield encoded()

    response = await client.put(
        url + "/audio", headers={**headers, "Content-Type": "audio/webm"}, content=chunks()
    )
    assert response.status_code == 404
    assert list(tmp_path.iterdir()) == []
    assert await session.get(SpeakingAttempt, attempt["id"]) is None


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


@pytest.mark.asyncio
@pytest.mark.parametrize("committed", [True, False])
async def test_commit_failure_never_deletes_confirmed_file(
    client, session, tmp_path, monkeypatch, committed
):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers = await conta(client, f"commit-{committed}")
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={
                "cue_id": await cue_id(client),
                "duration_ms": 1000,
                "consent": True,
            },
        )
    ).json()
    url = f"/api/speaking/attempts/{attempt['id']}/audio"
    original = AsyncSession.commit
    calls = 0

    async def uncertain_commit(self):
        nonlocal calls
        calls += 1
        if calls == 2:
            if committed:
                await original(self)
            raise ConnectionError("synthetic lost commit response")
        await original(self)

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "commit", uncertain_commit)
        failed = await client.put(
            url, headers={**headers, "Content-Type": "audio/webm"}, content=encoded()
        )
        assert failed.status_code == 503
    assert len(list(tmp_path.iterdir())) == int(committed)
    retry = await client.put(
        url, headers={**headers, "Content-Type": "audio/webm"}, content=encoded()
    )
    assert retry.status_code == 200
    assert len(list(tmp_path.iterdir())) == 1
    assert (
        await session.scalar(
            select(func.count())
            .select_from(SkillEvidence)
            .where(
                SkillEvidence.source_type == "speaking_attempt",
                SkillEvidence.source_id == attempt["id"],
            )
        )
        == 1
    )


@pytest.mark.asyncio
async def test_other_owner_cannot_even_stream_into_attempt(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    owner = await conta(client, "private-upload")
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=owner,
            json={
                "cue_id": await cue_id(client),
                "duration_ms": 1000,
                "consent": True,
            },
        )
    ).json()
    intruder = await conta(client, "wrong-upload-owner")

    async def chunks():
        pytest.fail("Não ler corpo de upload alheio")
        yield b"never"

    response = await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**intruder, "Content-Type": "audio/webm"},
        content=chunks(),
    )
    assert response.status_code == 404
    assert not list(tmp_path.iterdir())


async def cue_id(client: AsyncClient) -> int:
    lesson = (await client.get("/api/lessons/31")).json()
    return lesson["media"][0]["cues"][0]["id"]


async def course_cue_id(client: AsyncClient, course: str, lesson: int) -> int:
    response = await client.get(f"/api/courses/{course}/lessons/{lesson}")
    assert response.status_code == 200, response.text
    return response.json()["media"][0]["cues"][0]["id"]


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
async def test_listagem_paginada_e_estavel_com_datas_empatadas(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await conta(client, "pagina")
    user = await session.scalar(select(User).where(User.email == "speaking-pagina@exemplo.com"))
    cue = await session.get(TranscriptCue, await cue_id(client))
    assert user is not None and cue is not None
    tied_at = datetime(2026, 10, 15, 12, tzinfo=UTC)
    attempts = [
        SpeakingAttempt(
            user_id=user.id,
            transcript_cue_id=cue.id,
            duration_ms=1000 + number,
            status="ready",
            created_at=tied_at,
        )
        for number in range(5)
    ]
    session.add_all(attempts)
    session.add(
        SpeakingAttempt(
            user_id=user.id,
            transcript_cue_id=cue.id,
            duration_ms=2000,
            status="pending",
            created_at=tied_at,
        )
    )
    other_headers = await conta(client, "pagina-outra")
    other_user = await session.scalar(
        select(User).where(User.email == "speaking-pagina-outra@exemplo.com")
    )
    assert other_user is not None
    other_attempt = SpeakingAttempt(
        user_id=other_user.id,
        transcript_cue_id=cue.id,
        duration_ms=3000,
        status="ready",
        created_at=tied_at,
    )
    session.add(other_attempt)
    await session.commit()
    expected_ids = sorted((item.id for item in attempts), reverse=True)
    monkeypatch.setattr(get_settings(), "performance_probe_enabled", True)

    found: list[int] = []
    cursor: str | None = None
    for expected_size in (2, 2, 1):
        response = await client.get(
            "/api/speaking/attempts/page",
            headers=headers,
            params={
                "course": "voa-level-1",
                "unit": "31-40",
                "limit": 2,
                **({"cursor": cursor} if cursor else {}),
            },
        )
        assert response.status_code == 200, response.text
        assert int(response.headers[SQL_HEADER]) == 5
        assert int(response.headers[POOL_HEADER]) <= 1
        assert int(response.headers[BYTES_HEADER]) == len(response.content)
        body = response.json()
        assert len(body["items"]) == expected_size
        found.extend(item["id"] for item in body["items"])
        cursor = body["next_cursor"]

    assert found == expected_ids
    assert cursor is None
    invalid = await client.get(
        "/api/speaking/attempts/page?cursor=not-a-cursor",
        headers=headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_cursor"
    other_page = (await client.get("/api/speaking/attempts/page", headers=other_headers)).json()
    assert [item["id"] for item in other_page["items"]] == [other_attempt.id]
    assert not set(found).intersection(item["id"] for item in other_page["items"])


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

    audio = encoded()
    uploaded = await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm;codecs=opus"},
        content=audio,
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "ready"
    assert uploaded.json()["file_size"] == len(audio)
    # Duração declarada de 1700 ms não é a autoridade: o servidor decodifica ~1 s.
    assert 1000 <= uploaded.json()["duration_ms"] <= 1001
    assert len(list(tmp_path.iterdir())) == 1

    listed = (await client.get("/api/speaking/attempts?lesson=31", headers=headers)).json()
    assert [item["id"] for item in listed] == [attempt["id"]]
    assert listed[0]["course_slug"] == "voa-level-1"
    assert listed[0]["course_title"] == "Let's Learn English — Level 1"
    assert listed[0]["unit_slug"] == "31-40"
    assert listed[0]["lesson_number"] == 31
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
async def test_listagem_isola_gravacoes_quando_numero_da_aula_se_repete(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Aula 1 existe nos dois cursos, então a listagem precisa do curso para desempatar."""
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers = await conta(client, "cursos-mesmo-numero")
    attempt_ids: list[int] = []
    try:
        level_1_cue = await course_cue_id(client, "voa-level-1", 1)
        level_2_cue = await course_cue_id(client, "voa-level-2", 1)
        assert level_1_cue != level_2_cue
        for cue, audio in (
            (level_1_cue, encoded()),
            (level_2_cue, encoded(milliseconds=500)),
        ):
            created = await client.post(
                "/api/speaking/attempts",
                headers=headers,
                json={
                    "cue_id": cue,
                    "duration_ms": 1000,
                    "self_rating": "almost",
                    "consent": True,
                },
            )
            assert created.status_code == 201, created.text
            attempt_id = created.json()["id"]
            attempt_ids.append(attempt_id)
            uploaded = await client.put(
                f"/api/speaking/attempts/{attempt_id}/audio",
                headers={**headers, "Content-Type": "audio/webm"},
                content=audio,
            )
            assert uploaded.status_code == 200, uploaded.text

        level_1_items = (
            await client.get(
                "/api/speaking/attempts?lesson=1&course=voa-level-1",
                headers=headers,
            )
        ).json()
        level_2_items = (
            await client.get(
                "/api/speaking/attempts?lesson=1&course=voa-level-2",
                headers=headers,
            )
        ).json()
        legacy_items = (await client.get("/api/speaking/attempts?lesson=1", headers=headers)).json()

        assert [item["course_slug"] for item in level_1_items] == ["voa-level-1"]
        assert [item["course_slug"] for item in level_2_items] == ["voa-level-2"]
        assert [item["course_slug"] for item in legacy_items] == ["voa-level-1"]
    finally:
        for attempt_id in attempt_ids:
            await client.delete(f"/api/speaking/attempts/{attempt_id}", headers=headers)


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

    monkeypatch.setattr(settings, "speaking_max_bytes", 2_000_000)
    accepted = await client.put(
        f"/api/speaking/attempts/{attempt_id}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=encoded(),
    )
    repeated = await client.put(
        f"/api/speaking/attempts/{attempt_id}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=encoded(milliseconds=500),
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
        content=encoded(),
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
    assert (await client.get("/api/assist/status", headers=headers)).json()["used_today"] == 1


@pytest.mark.asyncio
async def test_stt_uses_captured_cue_after_editorial_change(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.test/stt")
    headers = await conta(client, "snapshot-stt")
    cue = await cue_id(client)
    original = await session.scalar(select(TranscriptCue.text_en).where(TranscriptCue.id == cue))
    assert original
    monkeypatch.setattr(
        assistance,
        "call_transcription_provider",
        lambda *args, **kwargs: assistance.TranscriptionResult(
            text=original,
            words=[{"text": original, "start_ms": 0, "end_ms": 500, "confidence": 0.95}],
            mean_confidence=0.95,
            cost_microusd=0,
        ),
    )
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={"cue_id": cue, "duration_ms": 1000, "consent": True},
        )
    ).json()
    await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=encoded(),
    )
    requested = await client.post(
        f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers
    )
    assert requested.status_code == 202
    await session.execute(
        update(TranscriptCue)
        .where(TranscriptCue.id == cue)
        .values(text_en="CURRENT EDITORIAL TEXT MUST NOT REPLACE HISTORY")
    )
    await session.commit()
    try:
        assert await transcription_queue.process_next_transcription() is True
        listed = (await client.get("/api/speaking/attempts", headers=headers)).json()[0]
        assert listed["cue_text"] == original
        assert listed["historical_content_status"] == "available"
        assert listed["transcription"]["expected_text"] == original
        assert listed["transcription"]["similarity_score"] == 1
    finally:
        await session.execute(
            update(TranscriptCue).where(TranscriptCue.id == cue).values(text_en=original)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_stt_refuses_legacy_attempt_without_snapshot_before_reserving_quota(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.test/stt")
    monkeypatch.setattr(settings, "editorial_snapshots_enabled", False)
    headers = await conta(client, "legacy-stt")
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={"cue_id": await cue_id(client), "duration_ms": 1000, "consent": True},
        )
    ).json()
    await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=encoded(),
    )
    monkeypatch.setattr(settings, "editorial_snapshots_enabled", True)
    response = await client.post(
        f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "historical_content_unavailable"
    assert await session.scalar(select(func.count()).select_from(TranscriptionJob)) == 0


@pytest.mark.asyncio
async def test_worker_fails_closed_for_legacy_job_without_calling_provider(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.test/stt")
    monkeypatch.setattr(settings, "editorial_snapshots_enabled", False)
    headers = await conta(client, "legacy-worker")
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={"cue_id": await cue_id(client), "duration_ms": 1000, "consent": True},
        )
    ).json()
    await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=encoded(),
    )

    original_lookup = speaking_api._captured_cue_text

    async def legacy_admission(*args, **kwargs):
        return "legacy admission before snapshot enforcement"

    monkeypatch.setattr(speaking_api, "_captured_cue_text", legacy_admission)
    requested = await client.post(
        f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers
    )
    assert requested.status_code == 202
    monkeypatch.setattr(speaking_api, "_captured_cue_text", original_lookup)
    monkeypatch.setattr(
        assistance,
        "call_transcription_provider",
        lambda *args, **kwargs: pytest.fail("provider must not receive legacy audio"),
    )

    assert await transcription_queue.process_next_transcription() is True
    result = (await client.get("/api/speaking/attempts", headers=headers)).json()[0]
    assert result["historical_content_status"] == "unavailable"
    assert result["transcription"]["status"] == "failed"
    assert result["transcription"]["error_code"] == "historical_content_unavailable"
    assert result["transcription"]["expected_text"] is None


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
        content=encoded(),
    )
    await client.post(f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers)
    assert await transcription_queue.process_next_transcription() is True
    item = (await client.get("/api/speaking/attempts", headers=headers)).json()[0]
    assert item["transcription"]["status"] == "failed"
    assert item["transcription"]["error_code"] == "provider_unavailable"
    assert (
        await client.get(f"/api/speaking/attempts/{attempt['id']}/audio", headers=headers)
    ).content == encoded()


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
        content=encoded(),
    )
    requested = (
        await client.post(f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers)
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
    balance = (await client.get("/api/assist/status", headers=headers)).json()
    assert balance["used_today"] == balance["consumed_today"] == 1
    assert balance["reserved_today"] == 0
    assert balance["cost_incomplete"] is False


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
        content=encoded(),
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
        content=encoded(),
    )
    requested = (
        await client.post(f"/api/speaking/attempts/{attempt['id']}/transcription", headers=headers)
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
