"""Compensa falha de upload somente quando o SQL confirma que não há referência."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SpeakingAttempt
from app.services.audio_storage import AudioStorage


async def discard_unreferenced_audio(
    session: AsyncSession, storage: AudioStorage, key: str
) -> None:
    """Um commit pode ter ocorrido mesmo se sua confirmação se perdeu na conexão."""
    try:
        await session.rollback()
        referenced = await session.scalar(
            select(SpeakingAttempt.id).where(SpeakingAttempt.storage_key == key)
        )
        if referenced is None:
            storage.delete(key)
    except Exception:
        # Preservar para reconciliação se o banco não puder confirmar a ausência.
        pass
