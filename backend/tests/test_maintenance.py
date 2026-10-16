import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.db.models import (
    AssistReservation,
    RefreshSession,
    SpeakingAttempt,
    TranscriptionJob,
    User,
    WorkerHeartbeat,
)
from app.db.session import get_sessionmaker
from app.services import assist_quota, maintenance, transcription_queue
from tests.test_writing import conta


async def fixtures(session, *, jobs=0):
    now = datetime.now(UTC)
    user = User(
        email=f"maintenance-{uuid4().hex}@example.invalid",
        password_hash="disabled",
        display_name="Test",
    )
    session.add(user)
    await session.flush()
    cue = await session.scalar(text("SELECT min(id) FROM transcript_cue"))
    for i in range(jobs):
        attempt = SpeakingAttempt(
            user_id=user.id, transcript_cue_id=cue, duration_ms=900, status="pending"
        )
        session.add(attempt)
        await session.flush()
        reservation, _ = await assist_quota.reserve(
            session, user.id, str(uuid4()), "0" * 64, "transcription"
        )
        if i == 0:
            await assist_quota.consume(session, reservation.id)
            await assist_quota.record_cost(session, reservation.id, 7)
        session.add(
            TranscriptionJob(
                user_id=user.id,
                speaking_attempt_id=attempt.id,
                provider="test",
                idempotency_key=uuid4().hex,
                assist_reservation_id=reservation.id,
                expires_at=now - timedelta(seconds=1),
            )
        )
    await session.commit()
    return user.id, cue


async def test_retention_bounded_concurrent_preserves_consumption(session):
    user, _ = await fixtures(session, jobs=5)
    assert await maintenance.retention_batch("transcriptions", limit=2) == 2
    assert await session.scalar(select(func.count()).select_from(TranscriptionJob)) == 5
    await session.rollback()
    results = await asyncio.gather(
        *(maintenance.retention_batch("transcriptions", apply=True, limit=2) for _ in range(2))
    )
    assert sum(results) == 4
    assert await maintenance.retention_batch("transcriptions", apply=True, limit=2) == 1
    assert await maintenance.retention_batch("transcriptions", apply=True, limit=2) == 0
    balance = await assist_quota.usage(session, user)
    assert balance.consumed == 1 and balance.reserved == 0 and balance.cost == 7
    assert await session.scalar(select(func.count()).select_from(AssistReservation)) == 5


async def test_retention_protects_recent_refresh_and_ready_audio(session):
    user, cue = await fixtures(session)
    now = datetime.now(UTC)
    for days in (-9, -1, 1):
        session.add(
            RefreshSession(
                user_id=user,
                jti=uuid4().hex,
                family_id=uuid4().hex,
                expires_at=now + timedelta(days=days),
            )
        )
    for days, state, size in (
        (-9, "pending", None),
        (-1, "pending", None),
        (-9, "ready", 10),
        (-9, "pending", 10),
    ):
        session.add(
            SpeakingAttempt(
                user_id=user,
                transcript_cue_id=cue,
                duration_ms=900,
                status=state,
                file_size=size,
                created_at=now + timedelta(days=days),
            )
        )
    await session.commit()
    assert await maintenance.retention_batch("refresh", apply=True) == 1
    assert await maintenance.retention_batch("pending", apply=True) == 1
    assert await session.scalar(select(func.count()).select_from(RefreshSession)) == 2
    assert await session.scalar(select(func.count()).select_from(SpeakingAttempt)) == 3


async def test_expiry_releases_only_undispatched_reservations(session):
    user, _ = await fixtures(session)
    now = datetime.now(UTC)
    for state in ("reserved", "consumed", "released"):
        session.add(
            AssistReservation(
                user_id=user,
                request_key=uuid4().hex,
                fingerprint="0" * 64,
                provider_key=uuid4().hex,
                modality="writing",
                state=state,
                created_at=now - timedelta(hours=1),
                expires_at=now - timedelta(minutes=1),
            )
        )
    await session.commit()
    assert await maintenance.retention_batch("reservations", apply=True) == 1
    assert await maintenance.retention_batch("reservations", apply=True) == 0
    assert (await assist_quota.usage(session, user, now - timedelta(hours=1))).consumed == 1


@pytest.mark.parametrize("kind,limit", [("arbitrary", 1), ("pending", 0), ("refresh", 501)])
async def test_database_rejects_invalid_retention_even_bypassing_python(session, kind, limit):
    with pytest.raises(DBAPIError):
        await session.execute(
            text("SELECT public.aulas_retention_batch(:kind,:size,true)"),
            {"kind": kind, "size": limit},
        )
    await session.rollback()


async def test_worker_once_cleans_without_enabled_provider(session, monkeypatch):
    await fixtures(session, jobs=1)
    monkeypatch.setattr(get_settings(), "assisted_features_enabled", False)
    await transcription_queue.run_transcription_worker(once=True)
    assert await session.scalar(select(func.count()).select_from(TranscriptionJob)) == 0
    heartbeat = await session.get(WorkerHeartbeat, "transcription")
    assert heartbeat and heartbeat.maintenance_counts["transcriptions"] == 1


async def test_worker_recovers_database_failure_and_remains_cancellable(monkeypatch):
    sweep = AsyncMock(side_effect=[ConnectionError("private diagnostic"), {}])
    monkeypatch.setattr(maintenance, "sweep", sweep)
    monkeypatch.setattr(maintenance, "heartbeat", AsyncMock())
    monkeypatch.setattr(transcription_queue, "dispose_engine", AsyncMock())
    monkeypatch.setattr(
        transcription_queue.account_deletion,
        "process_file_batch",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        transcription_queue,
        "process_next_transcription",
        AsyncMock(side_effect=asyncio.CancelledError),
    )
    pause = AsyncMock()
    monkeypatch.setattr(transcription_queue.asyncio, "sleep", pause)
    with pytest.raises(asyncio.CancelledError):
        await transcription_queue.run_transcription_worker()
    assert sweep.await_count == 2
    assert 2 <= pause.await_args.args[0] <= 3


async def test_claim_ignores_expired_jobs_before_dispatch(session):
    await fixtures(session, jobs=1)
    assert await transcription_queue._claim_next_job(datetime.now(UTC)) is None


async def test_heartbeat_upsert_keeps_last_maintenance_counts(session):
    await session.execute(delete(WorkerHeartbeat))
    await session.commit()
    await maintenance.heartbeat({"transcriptions": 3})
    await maintenance.heartbeat()
    async with get_sessionmaker()() as fresh:
        row = await fresh.get(WorkerHeartbeat, "transcription")
        assert row and row.maintenance_counts == {"transcriptions": 3} and row.maintenance_at


async def test_additional_cleanup_is_opt_in(monkeypatch, session):
    batch = AsyncMock(return_value=0)
    monkeypatch.setattr(maintenance, "retention_batch", batch)
    monkeypatch.setattr(get_settings(), "maintenance_cleanup_enabled", False)
    deletion_metrics = {"account_deletions_pending", "account_deletions_failed"}
    assert set(await maintenance.sweep()) == {"transcriptions", "reservations"} | deletion_metrics
    monkeypatch.setattr(get_settings(), "maintenance_cleanup_enabled", True)
    assert set(await maintenance.sweep()) == set(maintenance.SCOPES) | deletion_metrics


async def test_worker_status_is_private_and_handles_stale_heartbeat(client, session, monkeypatch):
    headers = await conta(client, "worker-status")
    monkeypatch.setattr(get_settings(), "assisted_features_enabled", True)
    monkeypatch.setattr(get_settings(), "assist_transcription_url", "http://provider.test/stt")
    await session.execute(delete(WorkerHeartbeat))
    await session.commit()
    initial = (await client.get("/api/assist/status", headers=headers)).json()
    assert initial["worker_state"] == "unknown" and initial["queued_jobs"] == 0
    assert (await client.get("/api/assist/status")).status_code == 401
    await fixtures(session, jobs=1)  # outro usuário, sem exposição da sua fila
    await maintenance.heartbeat()
    fresh = (await client.get("/api/assist/status", headers=headers)).json()
    assert fresh["worker_state"] == "active" and fresh["queued_jobs"] == 0
    await session.execute(text("UPDATE worker_heartbeat SET seen_at = now() - interval '1 hour'"))
    await session.commit()
    assert (await client.get("/api/assist/status", headers=headers)).json()[
        "worker_state"
    ] == "stale"
