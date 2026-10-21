"""Reservas reais no PostgreSQL isolado; gateways simulados, nunca cobrança externa."""

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update

from app.core.config import get_settings
from app.db.models import (
    AssistReservation,
    SkillEvidence,
    TranscriptionJob,
    User,
    WritingFeedbackRecord,
)
from app.db.session import get_engine, get_sessionmaker
from app.services import assist_quota, assistance, transcription_queue
from tests.audio_samples import encoded
from tests.test_speaking import cue_id
from tests.test_writing import conta, proposta


@pytest.fixture
def providers(monkeypatch, tmp_path):
    settings = get_settings()
    for key, value in {
        "assisted_features_enabled": True,
        "assist_provider_kind": "gateway",
        "assist_writing_url": "http://provider.test/writing",
        "assist_transcription_url": "http://provider.test/stt",
        "assist_daily_quota": 3,
        "assist_job_max_attempts": 1,
        "editorial_snapshots_enabled": True,
        "speaking_storage_dir": str(tmp_path),
    }.items():
        monkeypatch.setattr(settings, key, value)
    calls = []

    def writing(*args, **kwargs):
        calls.append(kwargs["idempotency_key"])
        return assistance.WritingAssistResult("Review the local criteria.", [], 0.5, 200)

    def transcribe(*args, **kwargs):
        calls.append(kwargs["idempotency_key"])
        return assistance.TranscriptionResult("Hello", [], 0.6, 100)

    monkeypatch.setattr(assistance, "call_writing_provider", writing)
    monkeypatch.setattr(assistance, "call_transcription_provider", transcribe)
    return calls


async def audio_attempt(client, headers):
    response = await client.post(
        "/api/speaking/attempts",
        headers=headers,
        json={
            "cue_id": await cue_id(client),
            "duration_ms": 900,
            "consent": True,
        },
    )
    assert response.status_code == 201
    attempt_id = response.json()["id"]
    response = await client.put(
        f"/api/speaking/attempts/{attempt_id}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=encoded(),
    )
    assert response.status_code == 200
    return attempt_id


async def status(client, headers):
    response = await client.get("/api/assist/status", headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_status_does_not_offer_transcription_without_snapshot_capture(
    client, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.test/stt")
    monkeypatch.setattr(settings, "editorial_snapshots_enabled", False)
    headers = await conta(client, "status-without-snapshot")
    assert (await status(client, headers))["transcription_enabled"] is False


@pytest.mark.parametrize("quota", [3, 5])
async def test_concurrent_modalities_share_atomic_quota(client, providers, monkeypatch, quota):
    monkeypatch.setattr(get_settings(), "assist_daily_quota", quota)
    headers = await conta(client, "quota-race")
    prompt = await proposta(client)
    attempts = [await audio_attempt(client, headers) for _ in range(4)]
    responses = await asyncio.gather(
        *(
            client.post(f"/api/speaking/attempts/{a}/transcription", headers=headers)
            for a in attempts
        ),
        *(
            client.post(
                f"/api/writing/prompts/{prompt['id']}/feedback",
                headers=headers,
                json={"text": f"My draft {i}.", "assisted": True, "operation_key": str(uuid4())},
            )
            for i in range(4)
        ),
    )
    # 503 é o desfecho desenhado para lock_timeout/pool esgotado sob contenção
    # (errors.database_error → service_unavailable): a requisição não é
    # admitida e nada é cobrado. Em máquina carregada ele aparece; o invariante
    # que importa é que a admissão para exatamente na cota e a contabilidade
    # bate, com ou sem timeouts.
    assert all(r.status_code in (200, 202, 429, 503) for r in responses)
    unavailable = sum(r.status_code == 503 for r in responses)
    admitted = sum(
        r.status_code == 202 or (r.status_code == 200 and r.json()["analysis_mode"] == "assisted")
        for r in responses
    )
    assert admitted == min(quota, len(responses) - unavailable)
    balance = await status(client, headers)
    assert balance["used_today"] == admitted
    assert balance["reserved_today"] + balance["consumed_today"] == admitted
    assert balance["remaining_today"] == quota - admitted
    assert len(providers) == balance["consumed_today"]


async def test_writing_replay_conflict_and_no_connection_during_provider(
    client, session, providers, monkeypatch
):
    headers = await conta(client, "writing-replay")
    prompt = await proposta(client)
    url = f"/api/writing/prompts/{prompt['id']}/feedback"
    body = {"text": "A draft.", "assisted": True, "operation_key": str(uuid4())}
    entered, finish = threading.Event(), threading.Event()

    def slow(*args, **kwargs):
        assert get_engine().pool.checkedout() == 0
        providers.append(kwargs["idempotency_key"])
        entered.set()
        assert finish.wait(10)
        return assistance.WritingAssistResult("Local criteria.", [], 0.5, 200)

    monkeypatch.setattr(assistance, "call_writing_provider", slow)
    task = asyncio.create_task(client.post(url, headers=headers, json=body))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        pending = await client.post(url, headers=headers, json=body)
        assert pending.status_code == 409
        assert (await status(client, headers))["cost_incomplete"] is True
    finally:
        finish.set()
    first = await task
    replay = await client.post(url, headers=headers, json=body)
    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert len(providers) == 1
    assert (
        await client.post(url, headers=headers, json={**body, "text": "Changed."})
    ).status_code == 409
    assert (
        await session.scalar(
            select(func.count())
            .select_from(SkillEvidence)
            .where(SkillEvidence.source_type == "writing_feedback")
        )
        == 1
    )
    await session.execute(delete(WritingFeedbackRecord))
    await session.commit()
    # Não reaproveita cota nem chama o provedor se o resultado foi removido.
    assert (await client.post(url, headers=headers, json=body)).status_code == 409
    balance = await status(client, headers)
    assert balance["consumed_today"] == 1
    assert balance["cost_microusd_today"] == 200
    assert balance["cost_incomplete"] is False


@pytest.mark.parametrize("when", ["queued", "completed", "failed", "audio_deleted"])
async def test_delete_releases_only_before_dispatch(client, providers, monkeypatch, when):
    headers = await conta(client, "cancel")
    attempt = await audio_attempt(client, headers)
    url = f"/api/speaking/attempts/{attempt}/transcription"
    first, duplicate = await asyncio.gather(
        client.post(url, headers=headers), client.post(url, headers=headers)
    )
    assert first.status_code == duplicate.status_code == 202
    assert first.json()["id"] == duplicate.json()["id"]
    assert (await status(client, headers))["reserved_today"] == 1
    if when in ("completed", "failed"):
        if when == "failed":

            def fail(*args, **kwargs):
                assert get_engine().pool.checkedout() == 0
                raise assistance.ProviderFailure("provider_unavailable")

            monkeypatch.setattr(assistance, "call_transcription_provider", fail)
        assert await transcription_queue.process_next_transcription()
    delete_url = (
        f"/api/speaking/attempts/{attempt}"
        if when == "audio_deleted"
        else f"/api/speaking/transcriptions/{first.json()['id']}"
    )
    assert (await client.delete(delete_url, headers=headers)).status_code == 204
    balance = await status(client, headers)
    assert balance["reserved_today"] == 0
    assert balance["consumed_today"] == int(when in ("completed", "failed"))
    assert balance["cost_incomplete"] == (when == "failed")
    assert balance["cost_microusd_today"] == (100 if when == "completed" else 0)


async def test_deleted_inflight_job_keeps_cost_without_recreating_text(
    client, providers, monkeypatch, session
):
    headers = await conta(client, "inflight-delete")
    attempt = await audio_attempt(client, headers)
    job = (
        await client.post(f"/api/speaking/attempts/{attempt}/transcription", headers=headers)
    ).json()
    entered, finish = threading.Event(), threading.Event()

    def slow(*args, **kwargs):
        assert get_engine().pool.checkedout() == 0
        entered.set()
        assert finish.wait(10)
        return assistance.TranscriptionResult("Private transcript", [], 0.7, 123)

    monkeypatch.setattr(assistance, "call_transcription_provider", slow)
    task = asyncio.create_task(transcription_queue.process_next_transcription())
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        assert (
            await client.delete(f"/api/speaking/transcriptions/{job['id']}", headers=headers)
        ).status_code == 204
    finally:
        finish.set()
    assert await task
    balance = await status(client, headers)
    assert balance["consumed_today"] == 1
    assert balance["cost_microusd_today"] == 123
    assert balance["cost_incomplete"] is False
    assert await session.scalar(select(func.count()).select_from(TranscriptionJob)) == 0


@pytest.mark.parametrize("expired", ["reservation", "job", "missing_audio"])
async def test_no_dispatch_without_live_reservation_and_audio(
    client, session, providers, tmp_path, expired
):
    headers = await conta(client, "expired")
    attempt = await audio_attempt(client, headers)
    await client.post(f"/api/speaking/attempts/{attempt}/transcription", headers=headers)
    if expired == "reservation":
        now = datetime.now(UTC)
        await session.execute(
            update(AssistReservation).values(
                created_at=now - timedelta(minutes=20), expires_at=now - timedelta(minutes=1)
            )
        )
    elif expired == "job":
        await session.execute(update(TranscriptionJob).values(expires_at=datetime.now(UTC)))
    else:
        for path in tmp_path.iterdir():
            path.unlink()
    await session.commit()
    if expired == "job":
        assert not await transcription_queue.process_next_transcription()
        # 39G: vencido nem chega a ser reivindicado; limpeza não depende da listagem.
        from app.services.maintenance import retention_batch

        assert await retention_batch("transcriptions", apply=True) == 1
    else:
        assert await transcription_queue.process_next_transcription()
    assert providers == []
    balance = await status(client, headers)
    assert balance["used_today"] == 0
    job = await session.scalar(select(TranscriptionJob))
    assert job is None if expired == "job" else job.status == "failed"


async def test_utc_boundary_expiry_and_other_account_isolation(client, session, providers):
    first = await conta(client, "first")
    second = await conta(client, "second")
    user = await session.scalar(select(User).where(User.email == "escrita-first@exemplo.com"))
    user_id = user.id
    await session.commit()
    fixed = datetime(2026, 10, 14, 0, 0, tzinfo=UTC)
    async with get_sessionmaker()() as separate:
        row, _ = await assist_quota.reserve(separate, user_id, "boundary", "hash", "writing")
        row.created_at = fixed - timedelta(seconds=1)
        row.expires_at = fixed + timedelta(seconds=10)
        row.state = "consumed"
        await separate.commit()
        assert (await assist_quota.usage(separate, user_id, fixed)).used == 0
        assert (await assist_quota.usage(separate, user_id, fixed - timedelta(seconds=1))).used == 1
        row.created_at = fixed
        row.state = "reserved"
        await separate.commit()
        assert (await assist_quota.usage(separate, user_id, fixed)).reserved == 1
        assert (await assist_quota.usage(separate, user_id, row.expires_at)).used == 0
        assert (await assist_quota.usage(separate, user_id, fixed)).resets_at == fixed + timedelta(
            days=1
        )
    assert (await status(client, second))["used_today"] == 0
    assert (await status(client, first))["quota_timezone"] == "UTC"


async def test_provider_failure_consumes_once_but_disabled_does_not(client, providers, monkeypatch):
    headers = await conta(client, "failed-writing")
    prompt = await proposta(client)
    url = f"/api/writing/prompts/{prompt['id']}/feedback"
    body = {"text": "Keep my draft.", "assisted": True, "operation_key": str(uuid4())}

    def fail(*args, **kwargs):
        providers.append(kwargs["idempotency_key"])
        raise assistance.ProviderFailure("provider_unavailable")

    monkeypatch.setattr(assistance, "call_writing_provider", fail)
    first = await client.post(url, headers=headers, json=body)
    replay = await client.post(url, headers=headers, json=body)
    assert first.json() == replay.json()
    assert first.json()["assisted_error_code"] == "provider_unavailable"
    assert len(providers) == 1
    assert (await status(client, headers))["cost_incomplete"] is True
    monkeypatch.setattr(get_settings(), "assisted_features_enabled", False)
    await client.post(url, headers=headers, json={**body, "operation_key": str(uuid4())})
    assert (await status(client, headers))["used_today"] == 1


async def test_expiry_during_uncommitted_dispatch_does_not_admit_extra_unit(
    client, session, providers, monkeypatch
):
    monkeypatch.setattr(get_settings(), "assist_daily_quota", 1)
    await conta(client, "expiry-race")
    user_id = await session.scalar(select(User.id))
    clock = [datetime(2026, 10, 14, 12, tzinfo=UTC)]

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(assist_quota, "datetime", FixedClock)
    reservation, _ = await assist_quota.reserve(session, user_id, "first", "hash", "writing")
    reservation_id, expires = reservation.id, reservation.expires_at
    await session.commit()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def dispatch():
        async with get_sessionmaker()() as separate, separate.begin():
            assert await assist_quota.consume(separate, reservation_id)
            await separate.flush()
            entered.set()
            await finish.wait()

    async def admit():
        async with get_sessionmaker()() as separate, separate.begin():
            try:
                await assist_quota.reserve(separate, user_id, "second", "hash", "writing")
            except assist_quota.QuotaExceeded:
                return False
            return True

    worker = asyncio.create_task(dispatch())
    contender = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        clock[0] = expires + timedelta(seconds=1)
        contender = asyncio.create_task(admit())
        done, _ = await asyncio.wait({contender}, timeout=0.2)
        assert not done, "A admissão precisa aguardar o despacho ainda não confirmado"
    finally:
        finish.set()
        await worker
    assert contender is not None and await contender is False


async def test_success_without_reported_cost_still_marks_partial(client, providers, monkeypatch):
    headers = await conta(client, "unknown-cost")
    prompt = await proposta(client)
    monkeypatch.setattr(
        assistance,
        "call_writing_provider",
        lambda *args, **kwargs: assistance.WritingAssistResult(
            "Local criteria.", [], 0.5, 0, cost_known=False
        ),
    )
    response = await client.post(
        f"/api/writing/prompts/{prompt['id']}/feedback",
        headers=headers,
        json={"text": "My draft.", "assisted": True},
    )
    assert response.json()["analysis_mode"] == "assisted"
    balance = await status(client, headers)
    assert balance["consumed_today"] == 1
    assert balance["cost_incomplete"] is True
