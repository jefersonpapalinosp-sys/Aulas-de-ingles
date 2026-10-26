"""Exclusão confirmada da conta e limpeza retomável dos arquivos de voz."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    AccountDeletionFile,
    AccountDeletionJob,
    DialogueTurn,
    Lesson,
    SpeakingAttempt,
    SpeakingDialogue,
    User,
)
from app.services import account_deletion
from app.services.audio_storage import AudioStorage
from tests.audio_samples import encoded
from tests.test_auth import auth, credenciais, registrar

CONFIRMATION = "EXCLUIR MINHA CONTA"


async def account_with_audio(
    client: AsyncClient,
    session: AsyncSession,
    suffix: str,
) -> tuple[dict[str, str], int, int, str]:
    headers = auth(await registrar(client, suffix))
    lesson = (await client.get("/api/lessons/31")).json()
    cue = lesson["media"][0]["cues"][0]["id"]
    attempt = (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={"cue_id": cue, "duration_ms": 900, "consent": True},
        )
    ).json()
    uploaded = await client.put(
        f"/api/speaking/attempts/{attempt['id']}/audio",
        headers={**headers, "Content-Type": "audio/webm"},
        content=encoded(),
    )
    assert uploaded.status_code == 200, uploaded.text
    row = await session.get(SpeakingAttempt, attempt["id"])
    assert row is not None and row.storage_key is not None
    return headers, row.user_id, row.id, row.storage_key


@pytest.mark.asyncio
async def test_wrong_password_does_not_delete_account(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    token = await registrar(client, "delete-wrong-password")
    response = await client.request(
        "DELETE",
        "/api/me/account",
        headers=auth(token),
        json={
            "operation_key": str(uuid4()),
            "password": "senha-incorreta",
            "confirmation": CONFIRMATION,
        },
    )
    assert response.status_code == 401
    assert (
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.email == credenciais("delete-wrong-password")["email"].lower())
        )
        == 1
    )
    assert await session.scalar(select(func.count()).select_from(AccountDeletionJob)) == 0


@pytest.mark.asyncio
async def test_delete_account_revokes_sessions_and_leaves_anonymous_receipt(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    token = await registrar(client, "delete-no-audio")
    operation_key = str(uuid4())

    response = await client.request(
        "DELETE",
        "/api/me/account",
        headers=auth(token),
        json={
            "operation_key": operation_key,
            "password": credenciais("delete-no-audio")["password"],
            "confirmation": CONFIRMATION,
        },
    )

    assert response.status_code == 202, response.text
    assert response.json() == {
        "operation_key": operation_key,
        "state": "completed",
        "database_deleted": True,
        "audio_files_pending": 0,
    }
    assert "no-store" in response.headers["cache-control"]
    assert "refresh_token=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert (await client.get("/api/auth/me", headers=auth(token))).status_code == 401
    assert (await client.post("/api/auth/refresh")).status_code == 401
    assert await session.scalar(select(func.count()).select_from(User)) == 0
    receipt = await session.get(AccountDeletionJob, operation_key)
    assert receipt is not None
    assert receipt.state == "completed"
    assert not hasattr(receipt, "user_id")
    assert not hasattr(receipt, "email")


@pytest.mark.asyncio
async def test_delete_account_cascades_rows_then_worker_removes_audio(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers, user_id, attempt_id, storage_key = await account_with_audio(
        client, session, "delete-audio"
    )
    path = tmp_path / storage_key
    assert path.is_file()
    # DB-45: um diálogo com turno de áudio apontando para a gravação acima.
    dialogue = SpeakingDialogue(
        user_id=user_id,
        lesson_id=await session.scalar(select(Lesson.id).order_by(Lesson.id).limit(1)),
        operation_key=str(uuid4()),
        mode="script",
        content_version=1,
        content_fingerprint="f" * 64,
        rubric_version="dialogue-prompt-v1",
    )
    session.add(dialogue)
    await session.flush()
    session.add(
        DialogueTurn(
            dialogue_id=dialogue.id,
            user_id=user_id,
            position=1,
            role="student",
            input_kind="audio",
            speaking_attempt_id=attempt_id,
            transcript="Thank you.",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    await session.commit()
    operation_key = str(uuid4())

    response = await client.request(
        "DELETE",
        "/api/me/account",
        headers=headers,
        json={
            "operation_key": operation_key,
            "password": credenciais("delete-audio")["password"],
            "confirmation": CONFIRMATION,
        },
    )

    assert response.status_code == 202, response.text
    assert response.json()["state"] == "cleanup_pending"
    assert response.json()["audio_files_pending"] == 1
    assert await session.get(User, user_id) is None
    assert await session.get(SpeakingAttempt, attempt_id) is None
    assert await session.scalar(select(func.count()).select_from(SpeakingDialogue)) == 0
    assert await session.scalar(select(func.count()).select_from(DialogueTurn)) == 0
    assert path.is_file(), "o commit do banco deve anteceder a limpeza assíncrona"
    assert await account_deletion.process_file_batch() == 1
    assert not path.exists()
    assert await session.scalar(select(func.count()).select_from(AccountDeletionFile)) == 0
    receipt = await session.get(AccountDeletionJob, operation_key)
    assert receipt is not None
    await session.refresh(receipt)
    assert receipt.state == "completed"
    assert receipt.deleted_file_count == receipt.file_count == 1


@pytest.mark.asyncio
async def test_audio_cleanup_stops_after_bounded_retries(
    client: AsyncClient,
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers, _, _, _ = await account_with_audio(client, session, "delete-retries")
    operation_key = str(uuid4())
    response = await client.request(
        "DELETE",
        "/api/me/account",
        headers=headers,
        json={
            "operation_key": operation_key,
            "password": credenciais("delete-retries")["password"],
            "confirmation": CONFIRMATION,
        },
    )
    assert response.status_code == 202
    await session.execute(
        update(AccountDeletionFile)
        .where(AccountDeletionFile.job_operation_key == operation_key)
        .values(
            attempt_count=account_deletion.MAX_FILE_ATTEMPTS - 1, next_attempt_at=datetime.now(UTC)
        )
    )
    await session.commit()

    def fail_delete(self: AudioStorage, key: str | None) -> None:
        raise OSError("synthetic unlink failure")

    monkeypatch.setattr(AudioStorage, "delete", fail_delete)
    assert await account_deletion.process_file_batch() == 1
    receipt = await session.get(AccountDeletionJob, operation_key)
    assert receipt is not None
    await session.refresh(receipt)
    assert receipt.state == "failed"
    assert receipt.last_error_code == "audio_delete_failed"
    assert await account_deletion.status_counts() == {
        "account_deletions_pending": 0,
        "account_deletions_failed": 1,
    }
    assert await account_deletion.process_file_batch() == 0
