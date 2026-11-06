"""Dados sintéticos exclusivos do ensaio público com marcador no banco."""

import asyncio
import io
import wave
from hashlib import sha256

from app.core.config import get_settings
from app.db.models import SpeakingAttempt, User
from app.db.session import dispose_engine, get_sessionmaker
from app.services.audio_storage import AudioStorage
from sqlalchemy import text

from ops.recovery_fixture import ensure_minimal_editorial


async def main():
    try:
        async with get_sessionmaker()() as session:
            marker = await session.scalar(
                text(
                    "SELECT shobj_description(oid,'pg_database') FROM pg_database "
                    "WHERE datname=current_database()"
                )
            )
            if marker != "aulas-ingles:public-recovery54:synthetic":
                raise RuntimeError("Fixture exige banco marcado exclusivamente para este ensaio.")
            user = User(
                email="recovery54@example.invalid",
                password_hash="!disabled!",
                display_name="Synthetic recovery",
            )
            session.add(user)
            await session.flush()
            cue, _, _, _ = await ensure_minimal_editorial(session)
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(b"\0\0" * 8000)
            payload = buffer.getvalue()
            key = AudioStorage(get_settings().speaking_storage_dir).save(payload, "audio/wav")
            session.add(
                SpeakingAttempt(
                    user_id=user.id,
                    transcript_cue_id=cue.id,
                    duration_ms=1000,
                    status="ready",
                    mime_type="audio/wav",
                    file_size=len(payload),
                    storage_key=key,
                    audio_sha256=sha256(payload).hexdigest(),
                    integrity_state="verified",
                )
            )
            await session.commit()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
