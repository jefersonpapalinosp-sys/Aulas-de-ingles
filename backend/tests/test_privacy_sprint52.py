"""Exclusão real de arquivos, recuperação e cascatas em banco descartável."""

from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import criar_token
from app.db.models import DialogueAudioDeletion, DialogueTurn, SpeakingAttempt, User
from app.services import account_deletion, dialogue_audio_cleanup, maintenance
from app.services.audio_storage import AudioStorage
from tests.test_auth import auth, credenciais, registrar
from tests.test_dialogue_retention import _turno_vencido


async def recording(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, expired: bool = False
) -> tuple[DialogueTurn, SpeakingAttempt, Path]:
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    turn = await _turno_vencido(session, vencido=expired)
    key = AudioStorage(str(tmp_path)).save(b"synthetic consented recording", "audio/webm")
    attempt = SpeakingAttempt(
        user_id=turn.user_id,
        origin="dialogue",
        duration_ms=900,
        storage_key=key,
        status="ready",
        mime_type="audio/webm",
    )
    session.add(attempt)
    await session.flush()
    turn.speaking_attempt_id = attempt.id
    turn.input_kind = "audio"
    await session.commit()
    return turn, attempt, tmp_path / key


async def test_delete_dialogue_erases_row_and_file_and_checks_owner(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turn, attempt, path = await recording(session, tmp_path, monkeypatch)
    other = auth(await registrar(client, "other-dialogue"))
    url = f"/api/speaking/dialogues/{turn.dialogue_id}"
    assert (await client.delete(url, headers=other)).status_code == 404
    assert path.is_file()
    response = await client.delete(url, headers=auth(criar_token(turn.user_id, "access")[0]))
    assert response.status_code == 204, response.text
    assert not path.exists()
    assert (
        await session.scalar(select(SpeakingAttempt.id).where(SpeakingAttempt.id == attempt.id))
        is None
    )
    assert await session.scalar(select(DialogueTurn.id).where(DialogueTurn.id == turn.id)) is None
    assert await session.scalar(select(func.count()).select_from(DialogueAudioDeletion)) == 0


async def test_failed_unlink_is_retried_without_restoring_dialogue(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turn, attempt, path = await recording(session, tmp_path, monkeypatch)
    original = AudioStorage.delete

    def fail(self: AudioStorage, key: str | None) -> None:
        raise OSError("synthetic failure")

    monkeypatch.setattr(AudioStorage, "delete", fail)
    assert (
        await client.delete(
            f"/api/speaking/dialogues/{turn.dialogue_id}",
            headers=auth(criar_token(turn.user_id, "access")[0]),
        )
    ).status_code == 204
    assert path.exists()
    assert (await dialogue_audio_cleanup.status_counts())["dialogue_audio_pending"] == 1
    assert (
        await session.scalar(select(SpeakingAttempt.id).where(SpeakingAttempt.id == attempt.id))
        is None
    )
    monkeypatch.setattr(AudioStorage, "delete", original)
    await session.execute(update(DialogueAudioDeletion).values(next_attempt_at=datetime.now(UTC)))
    await session.commit()
    assert await dialogue_audio_cleanup.process_batch(limit=10) == 1
    assert not path.exists()
    assert await dialogue_audio_cleanup.process_batch(limit=10) == 0


@pytest.mark.parametrize("expired", [True, False])
async def test_audio_retention_uses_turn_deadline_and_preserves_evidence(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expired: bool,
) -> None:
    turn, attempt, path = await recording(session, tmp_path, monkeypatch, expired=expired)
    assert await maintenance.retention_batch("dialogue_audio", apply=False) == int(expired)
    assert path.exists()
    monkeypatch.setattr(get_settings(), "maintenance_cleanup_enabled", False)
    counts = await maintenance.sweep()
    assert counts["dialogue_audio"] == int(expired)
    await dialogue_audio_cleanup.process_batch(limit=10)
    assert path.exists() is not expired
    await session.refresh(turn)
    assert turn.checks and turn.human_rating == "helpful"
    assert (turn.speaking_attempt_id is None) is expired
    assert await maintenance.retention_batch("dialogue_audio", apply=True) == 0


async def test_old_orphans_are_bounded_and_dry_run_does_not_delete(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turn, _, path = await recording(session, tmp_path, monkeypatch)
    await session.execute(delete(DialogueTurn).where(DialogueTurn.id == turn.id))
    await session.commit()
    assert await maintenance.retention_batch("dialogue_audio", apply=False, limit=1) == 1
    assert path.exists()
    assert await maintenance.retention_batch("dialogue_audio", apply=True, limit=1) == 1
    assert path.exists(), "a tarefa deve estar confirmada antes de remover bytes"
    await dialogue_audio_cleanup.process_batch()
    assert not path.exists()


async def test_rollback_preserves_recording_and_does_not_queue(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, attempt, path = await recording(session, tmp_path, monkeypatch)
    attempt_id = attempt.id
    await session.execute(delete(SpeakingAttempt).where(SpeakingAttempt.id == attempt_id))
    assert await session.scalar(select(func.count()).select_from(DialogueAudioDeletion)) == 1
    await session.rollback()
    assert await session.get(SpeakingAttempt, attempt_id) is not None and path.exists()
    assert await session.scalar(select(func.count()).select_from(DialogueAudioDeletion)) == 0


async def test_cleanup_failure_is_bounded_and_visible(session, tmp_path, monkeypatch):
    _, attempt, _ = await recording(session, tmp_path, monkeypatch)
    await session.execute(delete(SpeakingAttempt).where(SpeakingAttempt.id == attempt.id))
    await session.execute(
        update(DialogueAudioDeletion).values(attempt_count=dialogue_audio_cleanup.MAX_ATTEMPTS - 1)
    )
    await session.commit()

    def fail(self, key):
        raise OSError("synthetic failure")

    monkeypatch.setattr(AudioStorage, "delete", fail)
    assert await dialogue_audio_cleanup.process_batch() == 1
    assert await dialogue_audio_cleanup.process_batch() == 0
    assert await dialogue_audio_cleanup.status_counts() == {
        "dialogue_audio_pending": 0,
        "dialogue_audio_failed": 1,
    }


async def test_account_receipt_owns_audio_cleanup_without_duplicate_queue(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turn, _, path = await recording(session, tmp_path, monkeypatch)
    from app.core.security import hash_senha

    user = await session.get(User, turn.user_id)
    assert user
    user.password_hash = hash_senha("senha-bem-grande")
    await session.commit()
    response = await client.request(
        "DELETE",
        "/api/me/account",
        headers=auth(criar_token(turn.user_id, "access")[0]),
        json={
            "password": "senha-bem-grande",
            "confirmation": "EXCLUIR MINHA CONTA",
            "operation_key": str(uuid4()),
        },
    )
    assert response.status_code == 202, response.text
    assert response.json()["audio_files_pending"] == 1
    assert await session.scalar(select(func.count()).select_from(DialogueAudioDeletion)) == 0
    await account_deletion.process_file_batch()
    assert not path.exists()


async def test_account_with_ten_thousand_events_deletes_within_timeout(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    headers = auth(await registrar(client, "ten-thousand"))
    user_id = (await client.get("/api/auth/me", headers=headers)).json()["id"]
    anchor = str(uuid4())
    await session.execute(
        text("""
        INSERT INTO study_activity_session(id, user_id, lesson_id, started_at)
        VALUES (:anchor, :user, 31, now() - interval '2 days')
    """),
        {"anchor": anchor, "user": user_id},
    )
    await session.execute(
        text("""
        WITH events AS (
          INSERT INTO study_activity_event(user_id, session_id, operation_key, fingerprint,
                                           duration_ms, credited_ms)
          SELECT :user, :anchor, 's52-' || n, repeat('f', 64), 1000, 1000
            FROM generate_series(1, 10000) n RETURNING id
        ) INSERT INTO study_active_interval(event_id, user_id, lesson_id, starts_at, ends_at)
          SELECT id, :user, 31, now() - interval '1 day' + id * interval '2 seconds',
                 now() - interval '1 day' + id * interval '2 seconds' + interval '1 second'
          FROM events
    """),
        {"anchor": anchor, "user": user_id},
    )
    await session.commit()
    assert await session.scalar(text("SELECT count(*) FROM study_activity_event")) == 10000
    assert await session.scalar(text("SHOW statement_timeout")) == "30s"
    started = monotonic()
    response = await client.request(
        "DELETE",
        "/api/me/account",
        headers=headers,
        json={
            "operation_key": str(uuid4()),
            "password": credenciais("ten-thousand")["password"],
            "confirmation": "EXCLUIR MINHA CONTA",
        },
    )
    elapsed = monotonic() - started
    assert response.status_code == 202, response.text
    assert elapsed < 30
    assert await session.scalar(text("SELECT count(*) FROM study_activity_event")) == 0
    assert await session.scalar(text("SELECT count(*) FROM study_active_interval")) == 0
    print(f"Sprint 52: exclusão de 10000 eventos e intervalos em {elapsed:.3f}s")
