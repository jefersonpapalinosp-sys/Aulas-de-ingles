"""Portabilidade pessoal; somente leituras em snapshot consistente e limitado."""

import asyncio
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    AssistReservation,
    Course,
    CourseReview,
    CourseReviewAttempt,
    CourseUnit,
    DialogueTurn,
    EvidenceContentSnapshot,
    Exercise,
    ExerciseAttempt,
    Lesson,
    LessonMedia,
    LessonProgress,
    MediaProgress,
    NotebookEntry,
    PracticeSession,
    PracticeSessionItem,
    RefreshSession,
    ReviewCardLegacy,
    ReviewEvent,
    ReviewItem,
    SkillEvidence,
    SpeakingAttempt,
    SpeakingDialogue,
    StepProgress,
    StudyActiveInterval,
    StudyActivityEvent,
    StudyActivitySession,
    StudyPlan,
    StudySessionProgress,
    TranscriptCue,
    TranscriptionJob,
    User,
    WritingDraft,
    WritingFeedbackRecord,
    WritingPrompt,
    WritingRevision,
)
from app.schemas.notebook import AudioExportEntry, ExportScope, PersonalDataExportOut
from app.services.editorial_history import schema_available

MAX_RECORDS = 10_000
MAX_JSON_BYTES = 20 * 1024 * 1024
EXPORT_TIMEOUT_SECONDS = 20

# Lista deliberada: adicionar uma entidade pessoal exige revisar o contrato.
# Nenhuma serialização automática de colunas/objetos ORM ou credenciais.
PERSONAL_MODELS = (
    LessonProgress,
    StudySessionProgress,
    StudyPlan,
    MediaProgress,
    StudyActivitySession,
    StudyActivityEvent,
    StudyActiveInterval,
    SkillEvidence,
    ExerciseAttempt,
    ReviewItem,
    WritingDraft,
    WritingFeedbackRecord,
    SpeakingAttempt,
    TranscriptionJob,
    NotebookEntry,
    CourseReviewAttempt,
    PracticeSession,
    ReviewEvent,
    ReviewCardLegacy,
    AssistReservation,
    RefreshSession,
    EvidenceContentSnapshot,
    SpeakingDialogue,
    DialogueTurn,
)
CHILD_MODELS = (
    (WritingRevision, WritingDraft, "draft_id"),
    (StepProgress, StudySessionProgress, "study_session_id"),
    (PracticeSessionItem, PracticeSession, "practice_session_id"),
)


async def _inventory(session: AsyncSession, user_id: int, now: datetime) -> dict[str, int]:
    counts = {"app_user": 1}
    for model in PERSONAL_MODELS:
        if model is EvidenceContentSnapshot and not await schema_available(session):
            continue
        table = model.__table__
        query = select(func.count()).select_from(table).where(table.c.user_id == user_id)
        if model is TranscriptionJob:
            query = query.where(table.c.expires_at > now)
        counts[model.__tablename__] = int(await session.scalar(query) or 0)
    for child, parent, fk in CHILD_MODELS:
        table, owner = child.__table__, parent.__table__
        counts[child.__tablename__] = int(
            await session.scalar(
                select(func.count())
                .select_from(table.join(owner, table.c[fk] == owner.c.id))
                .where(owner.c.user_id == user_id)
            )
            or 0
        )
    if sum(counts.values()) > MAX_RECORDS:
        raise HTTPException(
            413,
            "Conta acima do limite da exportação síncrona. "
            "Nenhum arquivo parcial foi gerado. Solicite uma exportação assistida.",
        )
    return counts


async def _rows(
    session: AsyncSession,
    model: Any,
    fields: str,
    user_id: int,
    *,
    parent: Any = None,
    foreign_key: str | None = None,
) -> list[dict[str, Any]]:
    table = model.__table__
    query = select(*(table.c[name] for name in fields.split()))
    if parent is None:
        query = query.where(table.c.user_id == user_id)
    else:
        owner = parent.__table__
        assert foreign_key is not None
        query = query.select_from(table.join(owner, table.c[foreign_key] == owner.c.id))
        query = query.where(owner.c.user_id == user_id)
    return [dict(row) for row in (await session.execute(query.order_by(table.c.id))).mappings()]


async def _complete_export(
    session: AsyncSession,
    user_id: int,
    data: PersonalDataExportOut,
) -> None:
    if await schema_available(session):
        data.content_snapshots = await _rows(
            session,
            EvidenceContentSnapshot,
            "id user_id exercise_attempt_id practice_item_id writing_feedback_id "
            "speaking_attempt_id checkpoint_attempt_id schema_version content "
            "content_sha256 created_at",
            user_id,
        )
        exercise_snapshots = {
            row["exercise_attempt_id"]: row["id"]
            for row in data.content_snapshots
            if row["exercise_attempt_id"]
        }
        for attempt in data.exercise_attempts:
            if attempt["id"] in exercise_snapshots:
                attempt["historical_content_status"] = "available"
                attempt["content_snapshot_id"] = exercise_snapshots[attempt["id"]]
    data.checkpoint_attempts = await _rows(
        session,
        CourseReviewAttempt,
        "id review_id content_version answers result score total completed_at",
        user_id,
    )
    # Rotas e títulos atuais servem apenas para localizar o checkpoint. O resultado
    # persistido e content_version acima são os históricos, nunca recalculados.
    review, unit, course = CourseReview.__table__, CourseUnit.__table__, Course.__table__
    references = {
        row["id"]: dict(row)
        for row in (
            await session.execute(
                select(
                    review.c.id, course.c.slug.label("course_slug"), unit.c.slug.label("unit_slug")
                )
                .select_from(
                    review.join(unit, review.c.unit_id == unit.c.id).join(
                        course, unit.c.course_id == course.c.id
                    )
                )
                .where(review.c.id.in_({item["review_id"] for item in data.checkpoint_attempts}))
            )
        ).mappings()
    }
    for item in data.checkpoint_attempts:
        ref = references[item["review_id"]]
        item.update(course_slug=ref["course_slug"], unit_slug=ref["unit_slug"])
    data.practice_sessions = await _rows(
        session,
        PracticeSession,
        "id lesson_id source_session_id mode activity_type skill objective lesson_version "
        "content_fingerprint status current_position total_items state_revision started_at "
        "updated_at completed_at",
        user_id,
    )
    data.practice_items = await _rows(
        session,
        PracticeSessionItem,
        "id practice_session_id exercise_id position attempt_count first_try_correct "
        "highest_hint_level answer_revealed_at completed_at",
        user_id,
        parent=PracticeSession,
        foreign_key="practice_session_id",
    )
    data.writing_feedback = await _rows(
        session,
        WritingFeedbackRecord,
        "id prompt_id assist_reservation_id text word_count sentence_count ready checks "
        "algorithm_version rubric_version rubric_snapshot analysis_mode provider "
        "assisted_summary assisted_suggestions assisted_confidence assisted_cost_microusd "
        "assisted_error_code human_rating created_at",
        user_id,
    )
    data.review_events = await _rows(
        session,
        ReviewEvent,
        "id item_id quality algorithm_version before_state after_state created_at",
        user_id,
    )
    data.legacy_review_cards = await _rows(
        session,
        ReviewCardLegacy,
        "id vocab_item_id ease_factor interval_days repetitions lapses due_at "
        "last_reviewed_at created_at",
        user_id,
    )
    data.assistance_usage = await _rows(
        session,
        AssistReservation,
        "id modality state reason cost_microusd cost_known created_at expires_at dispatched_at",
        user_id,
    )
    # DB-45: diálogos e turnos do parceiro de conversa; o áudio de um turno é a
    # speaking_attempt referenciada e já consta em `speaking`/`audio_manifest`.
    data.dialogues = await _rows(
        session,
        SpeakingDialogue,
        "id lesson_id operation_key mode state partner_speaker content_version "
        "content_fingerprint provider_name rubric_version turn_limit started_at ended_at",
        user_id,
    )
    data.dialogue_turns = await _rows(
        session,
        DialogueTurn,
        "id dialogue_id position role input_kind speaking_attempt_id transcription_job_id "
        "state transcript checks partner_text hints confidence fallback cost_microusd "
        "error_code human_rating created_at completed_at expires_at",
        user_id,
    )
    data.login_sessions = await _rows(
        session, RefreshSession, "id created_at expires_at revoked_at", user_id
    )
    data.audio_manifest = [
        AudioExportEntry(
            attempt_id=item["id"],
            mime_type=item["mime_type"],
            file_size=item["file_size"],
            sha256=item["audio_sha256"],
            integrity_state=item["integrity_state"],
            download_path=(
                f"/api/speaking/attempts/{item['id']}/audio"
                if item["status"] == "ready"
                and item["integrity_state"] not in {"missing", "changed"}
                else None
            ),
        )
        for item in data.speaking
    ]


async def export_personal_data(session: AsyncSession, user_id: int) -> PersonalDataExportOut:
    """Requer sessão sem transação; autenticação permanece responsabilidade da rota.

    Uma conexão e uma transação read-only. Nenhum artefato privado fica no servidor.
    O limite rejeita a conta inteira, nunca oferece um arquivo truncado como completo.
    """
    try:
        async with asyncio.timeout(EXPORT_TIMEOUT_SECONDS):
            async with session.begin():
                await session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                await session.execute(text("SET LOCAL statement_timeout = '10s'"))
                now = await session.scalar(select(func.transaction_timestamp()))
                assert isinstance(now, datetime)
                user = await session.get(User, user_id)
                if user is None:
                    raise HTTPException(401, "Não autenticado.")
                counts = await _inventory(session, user_id, now)
                data = await _export_snapshot(session, user, now)
                await _complete_export(session, user_id, data)
                data.scope = ExportScope(
                    snapshot_at=now,
                    row_counts=counts,
                    exclusions=[
                        "Credenciais e identificadores de autenticação/fornecedores",
                        "Binários de áudio (baixar separadamente com autenticação)",
                        "Transcrições já expiradas no instante do snapshot",
                        "Rascunhos, gravações e respostas apenas neste dispositivo",
                        "Backups operacionais, logs e contadores agregados de segurança",
                    ],
                    historical_content_note="Versões e resultados persistidos são preservados. "
                    "content_snapshots contém apenas conteúdo efetivamente capturado. "
                    "Demais títulos, posições e cues são referências atuais. "
                    "Tentativas antigas podem não ter enunciado/gabarito original recuperável.",
                    audio_access_note="Caminhos relativos exigem a mesma conta autenticada. "
                    "Não são links públicos nem garantem disponibilidade futura. "
                    "A integridade é verificada novamente no download. "
                    "O arquivo JSON baixado não expira nem é apagado remotamente.",
                    max_records=MAX_RECORDS,
                    max_json_bytes=MAX_JSON_BYTES,
                )
                if len(data.model_dump_json().encode("utf-8")) > MAX_JSON_BYTES:
                    raise HTTPException(
                        413,
                        "Exportação acima de 20 MiB. Nenhum arquivo parcial "
                        "foi gerado. Solicite uma exportação assistida.",
                    )
                return data
    except TimeoutError:
        raise HTTPException(
            503, "A exportação demorou demais. Tente novamente mais tarde."
        ) from None
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == "57014":
            raise HTTPException(
                503, "A exportação demorou demais. Tente novamente mais tarde."
            ) from None
        raise


def _lesson_reference(lesson: Lesson) -> dict[str, str | int]:
    return {
        "lesson_id": lesson.id,
        "course_slug": lesson.course.slug,
        "unit_slug": lesson.unit.slug,
        "lesson_number": lesson.number,
    }


async def _export_snapshot(
    session: AsyncSession,
    usuario: User,
    snapshot_at: datetime,
) -> PersonalDataExportOut:
    progress = (
        await session.execute(
            select(LessonProgress)
            .where(LessonProgress.user_id == usuario.id)
            .order_by(LessonProgress.studied_at)
        )
    ).scalars()
    study_rows = (
        await session.execute(
            select(StudySessionProgress, Lesson)
            .join(Lesson, StudySessionProgress.lesson_id == Lesson.id)
            .where(StudySessionProgress.user_id == usuario.id)
            .order_by(Lesson.number)
        )
    ).all()
    attempt_rows = (
        await session.execute(
            select(ExerciseAttempt, Exercise, Lesson)
            .join(Exercise, ExerciseAttempt.exercise_id == Exercise.id)
            .join(Lesson, Exercise.lesson_id == Lesson.id)
            .where(ExerciseAttempt.user_id == usuario.id)
            .order_by(ExerciseAttempt.created_at)
        )
    ).all()
    review_rows = (
        await session.execute(
            select(ReviewItem, Lesson)
            .join(Lesson, ReviewItem.lesson_id == Lesson.id)
            .where(ReviewItem.user_id == usuario.id)
            .order_by(ReviewItem.created_at)
        )
    ).all()
    writing_rows = (
        await session.execute(
            select(WritingDraft, WritingPrompt, Lesson)
            .join(WritingPrompt, WritingDraft.prompt_id == WritingPrompt.id)
            .join(Lesson, WritingPrompt.lesson_id == Lesson.id)
            .where(WritingDraft.user_id == usuario.id)
            .order_by(WritingDraft.updated_at)
        )
    ).all()
    feedbacks = (
        await session.execute(
            select(WritingFeedbackRecord)
            .where(WritingFeedbackRecord.user_id == usuario.id)
            .order_by(WritingFeedbackRecord.created_at)
        )
    ).scalars()
    feedback_by_prompt: dict[int, list[WritingFeedbackRecord]] = {}
    for feedback in feedbacks:
        feedback_by_prompt.setdefault(feedback.prompt_id, []).append(feedback)
    speaking = list(
        (
            await session.execute(
                select(SpeakingAttempt)
                .options(
                    selectinload(SpeakingAttempt.cue)
                    .selectinload(TranscriptCue.media)
                    .selectinload(LessonMedia.lesson)
                )
                .where(SpeakingAttempt.user_id == usuario.id)
                .order_by(SpeakingAttempt.created_at)
            )
        ).scalars()
    )
    transcription_jobs = (
        await session.execute(
            select(TranscriptionJob).where(
                TranscriptionJob.user_id == usuario.id,
                TranscriptionJob.expires_at > snapshot_at,
            )
        )
    ).scalars()
    transcription_by_attempt = {job.speaking_attempt_id: job for job in transcription_jobs}
    notebook = (
        await session.execute(
            select(NotebookEntry)
            .where(NotebookEntry.user_id == usuario.id)
            .order_by(NotebookEntry.created_at)
        )
    ).scalars()
    plan = (
        await session.execute(select(StudyPlan).where(StudyPlan.user_id == usuario.id))
    ).scalar_one_or_none()
    step_rows = (
        await session.execute(
            select(StepProgress, StudySessionProgress, Lesson)
            .join(
                StudySessionProgress,
                StepProgress.study_session_id == StudySessionProgress.id,
            )
            .join(Lesson, StudySessionProgress.lesson_id == Lesson.id)
            .where(StudySessionProgress.user_id == usuario.id)
            .order_by(Lesson.number, StepProgress.id)
        )
    ).all()
    evidence = (
        await session.execute(
            select(SkillEvidence)
            .where(SkillEvidence.user_id == usuario.id)
            .order_by(SkillEvidence.occurred_at)
        )
    ).scalars()
    media_rows = (
        await session.execute(
            select(MediaProgress, LessonMedia, Lesson)
            .join(LessonMedia, MediaProgress.media_id == LessonMedia.id)
            .join(Lesson, LessonMedia.lesson_id == Lesson.id)
            .where(MediaProgress.user_id == usuario.id)
            .order_by(Lesson.number, LessonMedia.position)
        )
    ).all()

    return PersonalDataExportOut(
        schema_version="2.1",
        activity_sessions=[
            {"id": item.id, "lesson_id": item.lesson_id, "started_at": item.started_at}
            for item in (
                await session.scalars(
                    select(StudyActivitySession)
                    .where(StudyActivitySession.user_id == usuario.id)
                    .order_by(StudyActivitySession.started_at, StudyActivitySession.id)
                )
            )
        ],
        activity_events=[
            {
                "id": item.id,
                "session_id": item.session_id,
                "operation_key": item.operation_key,
                "duration_ms": item.duration_ms,
                "credited_ms": item.credited_ms,
                "received_at": item.received_at,
            }
            for item in (
                await session.scalars(
                    select(StudyActivityEvent)
                    .where(StudyActivityEvent.user_id == usuario.id)
                    .order_by(StudyActivityEvent.id)
                )
            )
        ],
        active_intervals=[
            {
                "id": item.id,
                "event_id": item.event_id,
                "lesson_id": item.lesson_id,
                "starts_at": item.starts_at,
                "ends_at": item.ends_at,
            }
            for item in (
                await session.scalars(
                    select(StudyActiveInterval)
                    .where(StudyActiveInterval.user_id == usuario.id)
                    .order_by(StudyActiveInterval.starts_at, StudyActiveInterval.id)
                )
            )
        ],
        exported_at=snapshot_at,
        profile={
            "id": usuario.id,
            "email": usuario.email,
            "display_name": usuario.display_name,
            "created_at": usuario.created_at,
        },
        lesson_progress=[
            {"id": item.id, **_lesson_reference(item.lesson), "studied_at": item.studied_at}
            for item in progress
        ],
        study_sessions=[
            {
                "id": item.id,
                **_lesson_reference(lesson),
                "current_step": item.current_step,
                "revision": item.revision,
                "completed_steps": item.completed_steps,
                "started_at": item.started_at,
                "total_seconds": item.total_seconds,
                "completed_at": item.completed_at,
                "updated_at": item.updated_at,
            }
            for item, lesson in study_rows
        ],
        study_plan=(
            {
                "id": plan.id,
                "weekly_minutes": plan.weekly_minutes,
                "preferred_days": plan.preferred_days,
                "goal": plan.goal,
                "timezone": plan.timezone,
                "created_at": plan.created_at,
                "updated_at": plan.updated_at,
            }
            if plan is not None
            else None
        ),
        step_progress=[
            {
                "id": step.id,
                "study_session_id": step.study_session_id,
                **_lesson_reference(lesson),
                "step": step.step,
                "seconds_spent": step.seconds_spent,
                "completed_at": step.completed_at,
                "updated_at": step.updated_at,
            }
            for step, _, lesson in step_rows
        ],
        media_progress=[
            {
                "id": progress.id,
                "media_id": media.id,
                **_lesson_reference(lesson),
                "media_label": media.label,
                "position_seconds": progress.position_seconds,
                "revision": progress.revision,
                "completed": progress.completed,
                "changed_at": progress.changed_at,
                "updated_at": progress.updated_at,
            }
            for progress, media, lesson in media_rows
        ],
        skill_evidence=[
            {
                "id": item.id,
                "skill": item.skill,
                "source_type": item.source_type,
                "source_id": item.source_id,
                "score": item.score,
                "occurred_at": item.occurred_at,
            }
            for item in evidence
        ],
        exercise_attempts=[
            {
                "id": attempt.id,
                "exercise_id": attempt.exercise_id,
                "practice_session_item_id": attempt.practice_session_item_id,
                "historical_content_status": "unavailable",
                **_lesson_reference(lesson),
                "exercise_position": exercise.position,
                "answer": attempt.answer,
                "correct": attempt.correct,
                "created_at": attempt.created_at,
            }
            for attempt, exercise, lesson in attempt_rows
        ],
        review_items=[
            {
                "id": item.id,
                "vocab_item_id": item.vocab_item_id,
                "legacy_card_id": item.legacy_card_id,
                "source_type": item.source_type,
                "source_id": item.source_id,
                "prompt_note": item.prompt_note,
                "media_url": item.media_url,
                "cue_start_seconds": item.cue_start_seconds,
                "cue_end_seconds": item.cue_end_seconds,
                "estimated_seconds": item.estimated_seconds,
                "suspended_at": item.suspended_at,
                "revision": item.revision,
                "ease_factor": item.ease_factor,
                "created_at": item.created_at,
                **_lesson_reference(lesson),
                "item_type": item.item_type,
                "skill": item.skill,
                "prompt": item.prompt,
                "answer": item.answer,
                "context": item.context,
                "origin_reason": item.origin_reason,
                "status": item.status,
                "interval_days": item.interval_days,
                "repetitions": item.repetitions,
                "lapses": item.lapses,
                "due_at": item.due_at,
                "last_reviewed_at": item.last_reviewed_at,
            }
            for item, lesson in review_rows
        ],
        writing=[
            {
                "id": draft.id,
                "prompt_id": prompt.id,
                "revision": draft.revision,
                **_lesson_reference(lesson),
                "prompt_title": prompt.title,
                "draft": draft.text,
                "updated_at": draft.updated_at,
                "revisions": [
                    {
                        "id": revision.id,
                        "version": revision.version,
                        "text": revision.text,
                        "created_at": revision.created_at,
                    }
                    for revision in draft.revisions
                ],
                "feedbacks": [
                    {
                        "id": feedback.id,
                        "text": feedback.text,
                        "word_count": feedback.word_count,
                        "sentence_count": feedback.sentence_count,
                        "ready": feedback.ready,
                        "checks": feedback.checks,
                        "algorithm_version": feedback.algorithm_version,
                        "rubric_version": feedback.rubric_version,
                        "rubric_snapshot": feedback.rubric_snapshot,
                        "analysis_mode": feedback.analysis_mode,
                        "provider": feedback.provider,
                        "assisted_summary": feedback.assisted_summary,
                        "assisted_suggestions": feedback.assisted_suggestions,
                        "assisted_confidence": feedback.assisted_confidence,
                        "assisted_cost_microusd": feedback.assisted_cost_microusd,
                        "assisted_error_code": feedback.assisted_error_code,
                        "human_rating": feedback.human_rating,
                        "created_at": feedback.created_at,
                    }
                    for feedback in feedback_by_prompt.get(prompt.id, [])
                ],
            }
            for draft, prompt, lesson in writing_rows
        ],
        speaking=[
            {
                "id": attempt.id,
                "cue_id": attempt.transcript_cue_id,
                "audio_sha256": attempt.audio_sha256,
                "integrity_state": attempt.integrity_state,
                "integrity_checked_at": attempt.integrity_checked_at,
                **_lesson_reference(attempt.cue.media.lesson),
                "cue_text": attempt.cue.text_en,
                "duration_ms": attempt.duration_ms,
                "self_rating": attempt.self_rating,
                "status": attempt.status,
                "mime_type": attempt.mime_type,
                "file_size": attempt.file_size,
                "consented_at": attempt.consented_at,
                "created_at": attempt.created_at,
                "transcription": (
                    {
                        "id": transcription_by_attempt[attempt.id].id,
                        "assist_reservation_id": transcription_by_attempt[
                            attempt.id
                        ].assist_reservation_id,
                        "attempt_count": transcription_by_attempt[attempt.id].attempt_count,
                        "error_code": transcription_by_attempt[attempt.id].error_code,
                        "status": transcription_by_attempt[attempt.id].status,
                        "provider": transcription_by_attempt[attempt.id].provider,
                        "transcript_text": transcription_by_attempt[attempt.id].transcript_text,
                        "words": transcription_by_attempt[attempt.id].words,
                        "mean_confidence": transcription_by_attempt[attempt.id].mean_confidence,
                        "similarity_score": transcription_by_attempt[attempt.id].similarity_score,
                        "low_confidence": transcription_by_attempt[attempt.id].low_confidence,
                        "cost_microusd": transcription_by_attempt[attempt.id].cost_microusd,
                        "human_rating": transcription_by_attempt[attempt.id].human_rating,
                        "requested_at": transcription_by_attempt[attempt.id].requested_at,
                        "completed_at": transcription_by_attempt[attempt.id].completed_at,
                        "expires_at": transcription_by_attempt[attempt.id].expires_at,
                    }
                    if attempt.id in transcription_by_attempt
                    else None
                ),
            }
            for attempt in speaking
        ],
        notebook=[
            {
                "id": entry.id,
                **_lesson_reference(entry.lesson),
                "kind": entry.kind,
                "content": entry.content,
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
            }
            for entry in notebook
        ],
    )
