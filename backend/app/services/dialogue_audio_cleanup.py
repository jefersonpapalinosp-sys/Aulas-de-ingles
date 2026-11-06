"""Limpeza retomável de gravações de diálogo já removidas do banco."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import DialogueAudioDeletion
from app.db.session import get_sessionmaker
from app.services.audio_storage import AudioStorage

MAX_ATTEMPTS = 10


async def process_batch(*, limit: int = 1, keys: list[str] | None = None) -> int:
    processed = 0
    for _ in range(min(limit, 500)):
        async with get_sessionmaker()() as session, session.begin():
            query = select(DialogueAudioDeletion).where(
                DialogueAudioDeletion.next_attempt_at <= func.now(),
                DialogueAudioDeletion.attempt_count < MAX_ATTEMPTS,
            )
            if keys is not None:
                query = query.where(DialogueAudioDeletion.storage_key.in_(keys))
            task = await session.scalar(
                query.order_by(
                    DialogueAudioDeletion.next_attempt_at, DialogueAudioDeletion.storage_key
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if task is None:
                break
            task.attempt_count += 1
            try:
                await asyncio.to_thread(
                    AudioStorage(get_settings().speaking_storage_dir).delete, task.storage_key
                )
            except (OSError, ValueError):
                task.last_error_code = "audio_delete_failed"
                task.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(3600, 2**task.attempt_count)
                )
            else:
                await session.delete(task)
            processed += 1
    return processed


async def status_counts() -> dict[str, int]:
    async with get_sessionmaker()() as session:
        pending, failed = (
            await session.execute(
                select(
                    func.count().filter(DialogueAudioDeletion.attempt_count < MAX_ATTEMPTS),
                    func.count().filter(DialogueAudioDeletion.attempt_count >= MAX_ATTEMPTS),
                )
            )
        ).one()
    return {"dialogue_audio_pending": pending, "dialogue_audio_failed": failed}
