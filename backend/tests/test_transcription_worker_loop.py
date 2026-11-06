import asyncio
import logging
from unittest.mock import AsyncMock, call

import pytest

from app.core.config import get_settings
from app.services import maintenance, transcription_queue


def _isolate_worker(monkeypatch: pytest.MonkeyPatch) -> tuple[AsyncMock, AsyncMock]:
    monkeypatch.setattr(
        transcription_queue.dialogue_audio_cleanup, "process_batch", AsyncMock(return_value=0)
    )
    heartbeat = AsyncMock()
    process = AsyncMock(return_value=True)
    monkeypatch.setattr(maintenance, "heartbeat", heartbeat)
    monkeypatch.setattr(
        transcription_queue.account_deletion,
        "process_file_batch",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(transcription_queue, "process_next_transcription", process)
    monkeypatch.setattr(transcription_queue, "dispose_engine", AsyncMock())
    return heartbeat, process


async def test_persistent_sweep_failure_keeps_heartbeat_and_claims_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "maintenance_interval_seconds", 2)
    sweep = AsyncMock(side_effect=RuntimeError("private maintenance diagnostic"))
    monkeypatch.setattr(maintenance, "sweep", sweep)
    heartbeat, process = _isolate_worker(monkeypatch)
    process.side_effect = [True, True, asyncio.CancelledError]
    monkeypatch.setattr(transcription_queue.time, "monotonic", lambda: process.await_count)

    with caplog.at_level(logging.WARNING), pytest.raises(asyncio.CancelledError):
        await transcription_queue.run_transcription_worker()

    assert sweep.await_count == 2
    assert heartbeat.await_count == 1
    assert process.await_count == 3
    assert "worker_maintenance_unavailable" in caplog.text
    assert "private maintenance diagnostic" not in caplog.text


async def test_sweep_recovery_updates_last_sweep_only_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "maintenance_interval_seconds", 1)
    counts = {"transcriptions": 2}
    sweep = AsyncMock(side_effect=[ConnectionError("private DSN"), counts])
    monkeypatch.setattr(maintenance, "sweep", sweep)
    heartbeat, process = _isolate_worker(monkeypatch)
    process.side_effect = [True, asyncio.CancelledError]
    monkeypatch.setattr(transcription_queue.time, "monotonic", lambda: process.await_count)

    with pytest.raises(asyncio.CancelledError):
        await transcription_queue.run_transcription_worker()

    assert heartbeat.await_args_list == [call(), call(counts)]
    assert process.await_count == 2
    # Uma disposição recupera a falha do sweep; outra pertence ao finally.
    assert transcription_queue.dispose_engine.await_count == 2


async def test_cancellation_during_sweep_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sweep = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(maintenance, "sweep", sweep)
    heartbeat, process = _isolate_worker(monkeypatch)

    with pytest.raises(asyncio.CancelledError):
        await transcription_queue.run_transcription_worker()

    heartbeat.assert_not_awaited()
    process.assert_not_awaited()
    transcription_queue.dispose_engine.assert_awaited_once()
