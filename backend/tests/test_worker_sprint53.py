import asyncio
import threading
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update

from app.core.config import get_settings
from app.db.models import (
    AssistReservation,
    DialogueTurn,
    SkillEvidence,
    SpeakingDialogue,
    TranscriptionJob,
)
from app.db.session import check_connection_budget, get_engine, get_sessionmaker
from app.services import assistance, dialogue
from app.services import transcription_queue as queue
from tests.test_dialogue_learning import fixture_dialogue


async def queued_dialogue(session, monkeypatch):
    _, _, conversation, _, _ = await fixture_dialogue(session, monkeypatch)
    turn, job = await dialogue.admit_turn(
        session,
        conversation,
        1,
        input_kind="text",
        transcript="I took the train today.",
        idempotency_key=str(uuid4()),
    )
    await session.commit()
    return conversation.id, turn.id, job.id


def slow_provider(monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    calls = []

    def reply(*args, **kwargs):
        calls.append(kwargs["idempotency_key"])
        entered.set()
        if not finish.wait(8):
            raise RuntimeError("synthetic provider timed out")
        return assistance.DialogueResult(
            raw={"partner_text": "Tell me more.", "hints": [], "confidence": 0.9},
            cost_microusd=7,
            cost_known=True,
        )

    monkeypatch.setattr(assistance, "call_dialogue_provider", reply)
    return entered, finish, calls


async def test_two_workers_do_not_duplicate_and_provider_holds_no_connection_or_dialogue_lock(
    session,
    monkeypatch,
):
    dialogue_id, turn_id, job_id = await queued_dialogue(session, monkeypatch)
    entered, finish, calls = slow_provider(monkeypatch)
    first = asyncio.create_task(queue.process_next_transcription())
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        assert get_engine().pool.checkedout() == 0
        assert await asyncio.wait_for(queue.process_next_transcription(), 2) is False
        async with get_sessionmaker()() as observer, observer.begin():
            await observer.execute(text("SET LOCAL lock_timeout='250ms'"))
            assert (
                await observer.scalar(
                    select(SpeakingDialogue.id)
                    .where(SpeakingDialogue.id == dialogue_id)
                    .with_for_update()
                )
                == dialogue_id
            )
        assert len(calls) == 1
    finally:
        finish.set()
        await first
    await session.rollback()
    assert (await session.get(DialogueTurn, turn_id)).state == "completed"
    assert (await session.get(TranscriptionJob, job_id)).attempt_count == 1


async def test_late_result_cannot_overwrite_new_claim_or_record_its_cost(session, monkeypatch):
    _, turn_id, job_id = await queued_dialogue(session, monkeypatch)
    entered, finish, _ = slow_provider(monkeypatch)
    first = asyncio.create_task(queue.process_next_transcription())
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        await session.execute(
            update(TranscriptionJob)
            .where(TranscriptionJob.id == job_id)
            .values(attempt_count=2, processing_started_at=datetime.now(UTC))
        )
        await session.commit()
    finally:
        finish.set()
        await first
    job = await session.get(TranscriptionJob, job_id)
    assert job.status == "processing" and job.attempt_count == 2
    assert (await session.get(DialogueTurn, turn_id)).state == "pending"
    assert await session.scalar(select(func.count()).select_from(SkillEvidence)) == 0
    reservation = await session.get(AssistReservation, job.assist_reservation_id)
    assert reservation.cost_microusd == 0


async def test_lease_prevents_duplicate_even_with_unsafe_legacy_stale_equal_timeout(
    session, monkeypatch
):
    await queued_dialogue(session, monkeypatch)
    # Boot rejeita isto; exercitamos também a renovação com settings legadas forçadas.
    monkeypatch.setattr(get_settings(), "assist_job_stale_seconds", 1)
    monkeypatch.setattr(get_settings(), "assist_timeout_seconds", 1)
    entered, finish, calls = slow_provider(monkeypatch)
    first = asyncio.create_task(queue.process_next_transcription())
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        await asyncio.sleep(1.3)
        assert not await queue.process_next_transcription()
        assert len(calls) == 1
    finally:
        finish.set()
        await first


async def test_poison_job_is_terminal_and_does_not_escape_consumer(session, monkeypatch):
    _, _, job_id = await queued_dialogue(session, monkeypatch)
    monkeypatch.setattr(
        queue, "_process_dialogue_claim", AsyncMock(side_effect=ValueError("private"))
    )
    assert await queue.process_next_transcription()
    row = await session.get(TranscriptionJob, job_id)
    assert row.status == "failed" and row.error_code == "unexpected_worker_error"
    assert row.attempt_count == 1
    assert not await queue.process_next_transcription()


async def test_heartbeat_runs_while_provider_waits(monkeypatch):
    finish = asyncio.Event()

    async def process():
        await finish.wait()
        return True

    async def heartbeat():
        finish.set()

    pulse = AsyncMock(side_effect=heartbeat)
    monkeypatch.setattr(queue, "process_next_transcription", process)
    monkeypatch.setattr(queue.maintenance, "heartbeat", pulse)
    assert await asyncio.wait_for(queue._process_with_heartbeat(interval=0.01), 1)
    pulse.assert_awaited_once()


async def test_stop_drains_active_job_without_claiming_another(monkeypatch):
    stop = asyncio.Event()
    completed = []

    async def process():
        stop.set()
        await asyncio.sleep(0.01)
        completed.append(True)
        return True

    process_mock = AsyncMock(side_effect=process)
    monkeypatch.setattr(queue.maintenance, "sweep", AsyncMock(return_value={}))
    monkeypatch.setattr(queue.maintenance, "heartbeat", AsyncMock())
    monkeypatch.setattr(queue.account_deletion, "process_file_batch", AsyncMock(return_value=0))
    monkeypatch.setattr(queue.dialogue_audio_cleanup, "process_batch", AsyncMock(return_value=0))
    monkeypatch.setattr(queue, "process_next_transcription", process_mock)
    monkeypatch.setattr(queue, "dispose_engine", AsyncMock())
    await queue.run_transcription_worker(stop_event=stop)
    assert completed == [True]
    process_mock.assert_awaited_once()


def test_stale_equal_timeout_is_rejected_before_any_worker_dispatch():
    settings = get_settings().model_copy(
        update={"assist_timeout_seconds": 20, "assist_job_stale_seconds": 20}
    )
    with pytest.raises(RuntimeError, match="2.*ASSIST_TIMEOUT_SECONDS"):
        settings.validar()
    settings.assist_job_stale_seconds = 55
    settings.validar()


async def test_capacity_check_and_idle_transaction_timeout(session, monkeypatch):
    await check_connection_budget()
    assert await session.scalar(text("SHOW idle_in_transaction_session_timeout")) == "1min"
    monkeypatch.setattr(get_settings(), "database_process_budget", 20)
    with pytest.raises(RuntimeError, match="Orçamento de conexões"):
        await check_connection_budget()


async def test_queue_migration_matches_runtime_and_is_repeatable(session):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from tests.test_privacy_migrations_sprint52 import migration

    module = migration("f53a1b8c9003_worker_queue_indexes.py")

    def exercise(connection):
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            for name, columns, predicate in module.NEW:
                assert module._exists(name, "transcription_job", columns, predicate)
            for name, columns, predicate in module.OLD:
                assert not module._exists(name, "transcription_job", columns, predicate)

    await (await session.connection()).run_sync(exercise)


async def test_api_boot_refuses_oversized_budget(session, monkeypatch):
    from app.main import create_app

    monkeypatch.setattr(get_settings(), "database_process_budget", 20)
    app = create_app()
    with pytest.raises(RuntimeError, match="Orçamento de conexões"):
        async with app.router.lifespan_context(app):
            pytest.fail("API iniciou com orçamento inválido")


async def test_postgres_lock_diagnostics_are_enabled(session):
    assert await session.scalar(text("SHOW log_lock_waits")) == "on"
    assert await session.scalar(text("SHOW log_parameter_max_length")) == "0"
    assert await session.scalar(text("SHOW log_parameter_max_length_on_error")) == "0"


async def test_unexpected_loop_error_is_sanitized_and_consumer_recovers(monkeypatch, caplog):
    stop = asyncio.Event()
    cleanup = AsyncMock(side_effect=[ValueError("private text must not leak"), 0])

    async def process():
        stop.set()
        return True

    monkeypatch.setattr(queue.maintenance, "sweep", AsyncMock(return_value={}))
    monkeypatch.setattr(queue.maintenance, "heartbeat", AsyncMock())
    monkeypatch.setattr(queue.account_deletion, "process_file_batch", cleanup)
    monkeypatch.setattr(queue.dialogue_audio_cleanup, "process_batch", AsyncMock(return_value=0))
    monkeypatch.setattr(queue, "process_next_transcription", process)
    monkeypatch.setattr(queue, "dispose_engine", AsyncMock())
    monkeypatch.setattr(queue.asyncio, "sleep", AsyncMock())
    await queue.run_transcription_worker(stop_event=stop)
    assert cleanup.await_count == 2
    assert "worker_iteration_failed" in caplog.text
    assert "private text must not leak" not in caplog.text
