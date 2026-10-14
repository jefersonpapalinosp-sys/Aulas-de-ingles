"""Somente laboratório vazio/guardado: uma voz WAV sintetizada, sem conteúdo de aluno."""

import asyncio
import io
import wave

from app.core.config import get_settings
from app.db.models import SpeakingAttempt, TranscriptCue, User
from app.db.session import dispose_engine, get_sessionmaker
from app.services.audio_storage import AudioStorage
from sqlalchemy import select


async def main():
    try:
        settings = get_settings()
        if (
            settings.app_env != "test"
            or "@source-db:5432/aulas_ingles_test" not in settings.database_url
        ):
            raise RuntimeError("Fixture só no laboratório de recuperação.")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"\0\0" * 8000)  # 1 s de silêncio, sem voz humana.
        payload = buffer.getvalue()
        async with get_sessionmaker()() as session:
            user = User(
                email="recovery-synthetic@example.invalid",
                password_hash="!disabled-synthetic!",
                display_name="Recovery synthetic",
            )
            session.add(user)
            await session.flush()
            cue = (
                await session.execute(select(TranscriptCue).order_by(TranscriptCue.id).limit(1))
            ).scalar_one()
            key = AudioStorage(settings.speaking_storage_dir).save(payload, "audio/wav")
            session.add(
                SpeakingAttempt(
                    user_id=user.id,
                    transcript_cue_id=cue.id,
                    duration_ms=1000,
                    status="ready",
                    mime_type="audio/wav",
                    file_size=len(payload),
                    storage_key=key,
                )
            )
            await session.commit()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
