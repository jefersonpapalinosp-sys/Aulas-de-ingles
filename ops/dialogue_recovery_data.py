"""Fixture e leitura pela aplicação; somente containers do laboratório INFRA-48."""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from app.api.health import current_schema_heads, required_schema_heads
from app.core.config import Settings, get_settings
from app.db.models import (
    AssistReservation,
    DialogueTurn,
    LessonMedia,
    SpeakingAttempt,
    SpeakingDialogue,
    TranscriptCue,
    TranscriptionJob,
    User,
)
from app.db.session import dispose_engine, get_sessionmaker
from app.services.audio_storage import AudioStorage
from app.services.dialogue_history import history_page
from app.services.personal_export import export_personal_data
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

DETAILS = {"target_terms": [{"text": "subway", "covered": True}], "grammar_patterns": []}


async def prepare(session: AsyncSession, settings: Settings, user: User) -> None:
    if (await session.scalars(select(SpeakingDialogue))).first() is not None:
        raise RuntimeError("Fixture de conversa já existe; nada será sobrescrito.")
    original = (await session.scalars(select(SpeakingAttempt))).one()
    assert original.storage_key is not None and original.audio_sha256 is not None
    storage = AudioStorage(settings.speaking_storage_dir)
    payload = storage.read_verified(
        original.storage_key, original.audio_sha256, settings.speaking_max_bytes
    )
    audio = SpeakingAttempt(
        user_id=user.id,
        origin="dialogue",
        duration_ms=1000,
        status="ready",
        mime_type="audio/wav",
        file_size=len(payload),
        storage_key=storage.save(payload, "audio/wav"),
        audio_sha256=sha256(payload).hexdigest(),
        integrity_state="verified",
    )
    lesson_id = (
        await session.execute(
            select(LessonMedia.lesson_id)
            .join(TranscriptCue, TranscriptCue.media_id == LessonMedia.id)
            .where(TranscriptCue.id == original.transcript_cue_id)
        )
    ).scalar_one()
    now = datetime.now(UTC)
    conversation = SpeakingDialogue(
        user_id=user.id,
        lesson_id=lesson_id,
        operation_key=str(uuid4()),
        mode="guided",
        state="completed",
        content_version=1,
        content_fingerprint="f" * 64,
        provider_name="synthetic-recovery48",
        rubric_version="dialogue-prompt-v1",
        started_at=now,
        ended_at=now,
    )
    session.add_all([audio, conversation])
    await session.flush()
    for position, kind, cost, rating in (
        (1, "text", 7, "not_helpful"),
        (2, "audio", 10, "helpful"),
    ):
        reservation = AssistReservation(
            user_id=user.id,
            request_key=str(uuid4()),
            fingerprint="f" * 64,
            modality="conversation",
            provider_key=uuid4().hex,
            state="consumed",
            cost_microusd=cost,
            cost_known=True,
            created_at=now,
            dispatched_at=now,
            expires_at=now + timedelta(hours=1),
        )
        session.add(reservation)
        await session.flush()
        job = TranscriptionJob(
            user_id=user.id,
            kind="dialogue",
            status="completed",
            provider="synthetic-recovery48",
            speaking_attempt_id=audio.id if kind == "audio" else None,
            assist_reservation_id=reservation.id,
            idempotency_key=uuid4().hex,
            cost_microusd=cost,
            expires_at=now + timedelta(days=30),
        )
        session.add(job)
        await session.flush()
        session.add(
            DialogueTurn(
                dialogue_id=conversation.id,
                user_id=user.id,
                position=position,
                role="student",
                input_kind=kind,
                speaking_attempt_id=audio.id if kind == "audio" else None,
                transcription_job_id=job.id,
                state="completed",
                transcript="The subway is faster.",
                partner_text="Where do you go?",
                checks={"target_terms_missing": True},
                check_details=DETAILS,
                cost_microusd=cost,
                human_rating=rating,
                created_at=now,
                completed_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
    await session.commit()


async def main(mode: str) -> dict[str, int | bool]:
    settings = get_settings()
    source = mode == "prepare"
    expected = (
        "@source-db:5432/aulas_ingles_test" if source else "@target-db:5432/aulas_ingles_restore"
    )
    if (
        mode not in {"prepare", "check"}
        or os.environ.get("DIALOGUE_RECOVERY_ONLY") != "disposable-recovery48"
        or settings.app_env != ("test" if source else "dev")
        or expected not in settings.database_url
    ):
        raise RuntimeError("Operação restrita ao laboratório INFRA-48.")
    try:
        async with get_sessionmaker()() as session:
            if not source:
                await session.execute(text("SET TRANSACTION READ ONLY"))
            if await current_schema_heads(session) != required_schema_heads():
                raise RuntimeError("Schema incompatível com a aplicação.")
            user = (await session.scalars(select(User))).one()
            if user.email != "recovery-synthetic@example.invalid":
                raise RuntimeError("Conta sintética não confirmada.")
            if source:
                await prepare(session, settings, user)
                return {"fixture_created": True}
            user_id = user.id
            page = await history_page(session, user_id, 10)
            assert len(page.items) == 1 and page.items[0].turns_remaining == 10
        async with get_sessionmaker()() as session:
            data = await export_personal_data(session, user_id)
        exported = data.model_dump()
        turns = exported["dialogue_turns"]
        assert len(exported["dialogues"]) == 1 and len(turns) == 2
        assert sum(t["cost_microusd"] for t in turns) == 17
        assert {t["human_rating"] for t in turns} == {"helpful", "not_helpful"}
        assert all(t["check_details"] == DETAILS for t in turns)
        assert all(t["transcript"] == "The subway is faster." for t in turns)
        async with get_sessionmaker()() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            audios = list((await session.scalars(select(SpeakingAttempt))).all())
            assert len(audios) == 2
            for audio in audios:
                assert audio.storage_key is not None and audio.audio_sha256 is not None
                payload = AudioStorage(settings.speaking_storage_dir).read_verified(
                    audio.storage_key,
                    audio.audio_sha256,
                    settings.speaking_max_bytes,
                )
                assert len(payload) == audio.file_size
        return {
            "verified": True,
            "dialogues": 1,
            "turns": 2,
            "audio_files": 2,
            "historical_checks": True,
            "ratings": True,
            "cost_microusd": 17,
            "history_read": True,
            "personal_export_read": True,
        }
    finally:
        await dispose_engine()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main(sys.argv[1])), sort_keys=True))
