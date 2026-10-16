"""Somente laboratório vazio/guardado: uma voz WAV sintetizada, sem conteúdo de aluno."""

import asyncio
import io
import wave
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from app.core.config import get_settings
from app.db.models import (
    Course,
    CourseUnit,
    Exercise,
    ExerciseAttempt,
    Lesson,
    LessonMedia,
    LessonProgress,
    MediaProgress,
    NotebookEntry,
    PracticeSession,
    PracticeSessionItem,
    ReviewItem,
    SpeakingAttempt,
    StepProgress,
    StudyActiveInterval,
    StudyActivityEvent,
    StudyActivitySession,
    StudySessionProgress,
    TranscriptCue,
    TranscriptionJob,
    User,
    WritingDraft,
    WritingFeedbackRecord,
    WritingPrompt,
    WritingRevision,
)
from app.db.session import dispose_engine, get_sessionmaker
from app.services.audio_storage import AudioStorage
from sqlalchemy import select


async def ensure_minimal_editorial(session):
    """Cria somente o grafo editorial necessário ao fixture de upgrade.

    O catálogo completo corrente não pode ser semeado numa revisão anterior:
    posições editoriais podem ter mudado desde então. Este grafo usa dados
    sintéticos, não concorre com o conteúdo real e é suficiente para cobrir as
    FKs das modalidades pessoais exercitadas pelo ensaio.
    """
    course = (
        await session.execute(select(Course).order_by(Course.id).limit(1))
    ).scalar_one_or_none()
    if course is None:
        course = Course(
            slug="upgrade-synthetic-course",
            title="Synthetic upgrade course",
            level="test",
            proficiency_label="Synthetic",
            provider="Recovery laboratory",
            source_url="https://example.invalid/upgrade-course",
            position=1,
            status="published",
            total_lessons=1,
        )
        session.add(course)
        await session.flush()

    unit = (
        await session.execute(
            select(CourseUnit)
            .where(CourseUnit.course_id == course.id)
            .order_by(CourseUnit.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if unit is None:
        unit = CourseUnit(
            course_id=course.id,
            slug="upgrade-synthetic-unit",
            title="Synthetic upgrade unit",
            position=1,
            status="published",
            lesson_start=31,
            lesson_end=31,
            total_lessons=1,
        )
        session.add(unit)
        await session.flush()

    lesson = (
        await session.execute(select(Lesson).order_by(Lesson.id).limit(1))
    ).scalar_one_or_none()
    if lesson is None:
        lesson = Lesson(
            course_id=course.id,
            unit_id=unit.id,
            number=31,
            slug="upgrade-synthetic-31",
            position=1,
            title="Synthetic recovery lesson",
            title_pt="Aula sintética de recuperação",
            voa_url="https://example.invalid/upgrade-lesson",
            grammar_tag="synthetic recovery",
            focus_points=["upgrade", "recovery"],
            lead="Synthetic editorial data for an isolated recovery rehearsal.",
            warmup_prompt="Prepare the isolated recovery rehearsal.",
            listening_focus="Confirm that references survive the upgrade.",
        )
        session.add(lesson)
        await session.flush()

    exercise = (
        await session.execute(
            select(Exercise)
            .where(Exercise.lesson_id == lesson.id)
            .order_by(Exercise.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if exercise is None:
        exercise = Exercise(
            lesson_id=lesson.id,
            position=1,
            activity_type="gap_fill",
            skill="grammar",
            objective="apply",
            prompt="Complete the synthetic recovery sentence.",
            explanation="Synthetic explanation used only by the isolated upgrade rehearsal.",
        )
        session.add(exercise)

    prompt = (
        await session.execute(
            select(WritingPrompt)
            .where(WritingPrompt.lesson_id == lesson.id)
            .order_by(WritingPrompt.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if prompt is None:
        prompt = WritingPrompt(
            lesson_id=lesson.id,
            position=1,
            title="Synthetic recovery writing",
            instructions="Write one synthetic sentence for the recovery rehearsal.",
            min_words=1,
            min_sentences=1,
            requirements=[],
        )
        session.add(prompt)

    media = (
        await session.execute(
            select(LessonMedia)
            .where(LessonMedia.lesson_id == lesson.id)
            .order_by(LessonMedia.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if media is None:
        media = LessonMedia(
            lesson_id=lesson.id,
            position=1,
            kind="audio",
            label="Synthetic recovery audio",
            source_url="https://example.invalid/synthetic-recovery.wav",
            license_status="permission_granted",
            license_note="Synthetic silence generated only for the isolated recovery rehearsal.",
            attribution="Recovery laboratory",
            offline_policy="cache_allowed",
            duration_seconds=1,
            transcript=[],
        )
        session.add(media)
    await session.flush()

    cue = (
        await session.execute(
            select(TranscriptCue)
            .where(TranscriptCue.media_id == media.id)
            .order_by(TranscriptCue.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if cue is None:
        cue = TranscriptCue(
            media_id=media.id,
            position=1,
            start_seconds=0,
            end_seconds=1,
            speaker="Synthetic",
            text_en="Synthetic recovery cue.",
            text_pt="Trecho sintético de recuperação.",
        )
        session.add(cue)
        await session.flush()
    return cue, exercise, prompt, media


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
        now = datetime.now(UTC)
        async with get_sessionmaker()() as session:
            user = User(
                email="recovery-synthetic@example.invalid",
                password_hash="!disabled-synthetic!",
                display_name="Recovery synthetic",
            )
            session.add(user)
            await session.flush()
            cue, exercise, prompt, media = await ensure_minimal_editorial(session)
            key = AudioStorage(settings.speaking_storage_dir).save(payload, "audio/wav")
            speaking = SpeakingAttempt(
                user_id=user.id,
                transcript_cue_id=cue.id,
                duration_ms=1000,
                status="ready",
                mime_type="audio/wav",
                file_size=len(payload),
                storage_key=key,
                audio_sha256=sha256(payload).hexdigest(),
                integrity_state="verified",
                integrity_checked_at=now,
            )
            journey = StudySessionProgress(
                user_id=user.id,
                lesson_id=exercise.lesson_id,
                current_step="assistir",
                revision=2,
                completed_steps=["preparar"],
                total_seconds=90,
            )
            practice = PracticeSession(
                user_id=user.id,
                lesson_id=exercise.lesson_id,
                idempotency_key="11111111-1111-4111-8111-111111111111",
                mode="guided",
                activity_type=exercise.activity_type,
                skill=exercise.skill,
                objective=exercise.objective,
                lesson_version=1,
                content_fingerprint="a" * 64,
                status="active",
                current_position=0,
                total_items=1,
                state_revision=2,
            )
            draft = WritingDraft(
                user_id=user.id,
                prompt_id=prompt.id,
                text="Synthetic draft for recovery rehearsal.",
                revision=1,
            )
            session.add_all([speaking, journey, practice, draft])
            await session.flush()
            practice_item = PracticeSessionItem(
                practice_session_id=practice.id,
                exercise_id=exercise.id,
                position=0,
                attempt_count=1,
                first_try_correct=False,
                highest_hint_level=0,
            )
            attempt = ExerciseAttempt(
                user_id=user.id,
                exercise_id=exercise.id,
                idempotency_key="22222222-2222-4222-8222-222222222222",
                answer="synthetic wrong answer",
                correct=False,
            )
            activity = StudyActivitySession(
                id="33333333-3333-4333-8333-333333333333",
                user_id=user.id,
                lesson_id=exercise.lesson_id,
                started_at=now - timedelta(seconds=20),
            )
            session.add_all([practice_item, attempt, activity])
            await session.flush()
            attempt.practice_session_item_id = practice_item.id
            event = StudyActivityEvent(
                user_id=user.id,
                session_id=activity.id,
                operation_key="44444444-4444-4444-8444-444444444444",
                fingerprint="b" * 64,
                duration_ms=10_000,
                credited_ms=10_000,
            )
            session.add(event)
            await session.flush()
            session.add_all(
                [
                    StepProgress(
                        study_session_id=journey.id,
                        step="preparar",
                        seconds_spent=60,
                        completed_at=now - timedelta(seconds=30),
                    ),
                    StepProgress(
                        study_session_id=journey.id,
                        step="assistir",
                        seconds_spent=30,
                    ),
                    WritingRevision(
                        draft_id=draft.id,
                        version=1,
                        text="Synthetic immutable writing version.",
                    ),
                    WritingFeedbackRecord(
                        user_id=user.id,
                        prompt_id=prompt.id,
                        text="Synthetic writing feedback input.",
                        word_count=4,
                        sentence_count=1,
                        ready=False,
                        checks=[],
                        algorithm_version="legacy-v1",
                        analysis_mode="deterministic",
                    ),
                    ReviewItem(
                        user_id=user.id,
                        lesson_id=exercise.lesson_id,
                        item_type="grammar_error",
                        source_type="exercise_attempt",
                        source_id=attempt.id,
                        source_key="recovery-synthetic-review",
                        skill=exercise.skill,
                        prompt="Synthetic recovery prompt",
                        answer="Synthetic recovery answer",
                        origin_reason="upgrade fixture",
                        due_at=now,
                    ),
                    StudyActiveInterval(
                        event_id=event.id,
                        user_id=user.id,
                        lesson_id=exercise.lesson_id,
                        starts_at=now - timedelta(seconds=10),
                        ends_at=now,
                    ),
                    MediaProgress(
                        user_id=user.id,
                        media_id=media.id,
                        position_seconds=12.5,
                        revision=1,
                        completed=False,
                        operation_key="55555555-5555-4555-8555-555555555555",
                        fingerprint="c" * 64,
                        changed_at=now,
                    ),
                    LessonProgress(user_id=user.id, lesson_id=exercise.lesson_id),
                    NotebookEntry(
                        user_id=user.id,
                        lesson_id=exercise.lesson_id,
                        kind="note",
                        content="Synthetic notebook entry for upgrade recovery.",
                    ),
                    TranscriptionJob(
                        user_id=user.id,
                        speaking_attempt_id=speaking.id,
                        status="queued",
                        provider="synthetic-disabled",
                        idempotency_key="d" * 64,
                        attempt_count=0,
                        max_attempts=3,
                        next_attempt_at=now,
                        expires_at=now + timedelta(days=1),
                    ),
                ]
            )
            await session.commit()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
