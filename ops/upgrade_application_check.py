"""Leitura pós-upgrade pela aplicação no clone DB-42; nunca imprime conteúdo."""

import asyncio
import json

from app.api.health import current_schema_heads, required_schema_heads
from app.core.config import get_settings
from app.db.models import SpeakingAttempt, User
from app.db.session import dispose_engine, get_sessionmaker
from app.services.audio_storage import AudioStorage
from sqlalchemy import func, select


async def check() -> dict[str, int | bool]:
    settings = get_settings()
    if (
        settings.app_env != "dev"
        or "@target-db:5432/aulas_ingles_restore" not in settings.database_url
        or settings.speaking_storage_dir != "/app/data/speaking"
    ):
        raise RuntimeError("Leitura permitida somente no clone DB-42.")
    try:
        async with get_sessionmaker()() as session:
            if await current_schema_heads(session) != required_schema_heads():
                raise RuntimeError("Schema pós-upgrade incompatível.")
            users = int(
                await session.scalar(select(func.count()).select_from(User)) or 0
            )
            attempt = (
                await session.execute(
                    select(SpeakingAttempt)
                    .where(SpeakingAttempt.storage_key.is_not(None))
                    .order_by(SpeakingAttempt.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if attempt is None or not attempt.storage_key or not attempt.file_size:
                raise RuntimeError("Referência sintética de voz ausente.")
            payload = AudioStorage(settings.speaking_storage_dir).read_verified(
                attempt.storage_key,
                attempt.audio_sha256,
                settings.speaking_max_bytes,
            )
            if len(payload) != attempt.file_size:
                raise RuntimeError("Leitura sintética de voz divergente.")
            return {"verified": True, "users": users, "audio_bytes": len(payload)}
    finally:
        await dispose_engine()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(check()), sort_keys=True))
