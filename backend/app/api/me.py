"""Caderno e portabilidade dos dados do aluno."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import UsuarioAtual
from app.api.review import adicionar_item_revisao, remover_item_por_origem
from app.db.models import (
    Exercise,
    ExerciseAttempt,
    Lesson,
    LessonMedia,
    LessonProgress,
    NotebookEntry,
    ReviewItem,
    SkillEvidence,
    SpeakingAttempt,
    StepProgress,
    StudyPlan,
    StudySessionProgress,
    TranscriptCue,
    TranscriptionJob,
    WritingDraft,
    WritingFeedbackRecord,
    WritingPrompt,
)
from app.db.session import get_session
from app.schemas.notebook import (
    NotebookEntryIn,
    NotebookEntryOut,
    NotebookEntryUpdate,
    NotebookKind,
    PersonalDataExportOut,
)

router = APIRouter(prefix="/me", tags=["me"])


def _entry_out(entry: NotebookEntry) -> NotebookEntryOut:
    return NotebookEntryOut(
        id=entry.id,
        lesson_number=entry.lesson.number,
        lesson_title=entry.lesson.title,
        kind=entry.kind,  # type: ignore[arg-type]
        content=entry.content,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


async def _owned_entry(session: AsyncSession, entry_id: int, user_id: int) -> NotebookEntry:
    entry = (
        await session.execute(
            select(NotebookEntry).where(
                NotebookEntry.id == entry_id,
                NotebookEntry.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anotação não existe.")
    return entry


@router.get("/notebook", response_model=list[NotebookEntryOut])
async def listar_caderno(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    lesson: Annotated[int | None, Query(ge=1)] = None,
    kind: Annotated[NotebookKind | None, Query()] = None,
) -> list[NotebookEntryOut]:
    query = select(NotebookEntry).where(NotebookEntry.user_id == usuario.id)
    if lesson is not None:
        query = query.where(NotebookEntry.lesson.has(number=lesson))
    if kind is not None:
        query = query.where(NotebookEntry.kind == kind)
    entries = (await session.execute(query.order_by(NotebookEntry.updated_at.desc()))).scalars()
    return [_entry_out(entry) for entry in entries]


@router.post("/notebook", response_model=NotebookEntryOut, status_code=status.HTTP_201_CREATED)
async def criar_anotacao(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[NotebookEntryIn, Body()],
) -> NotebookEntryOut:
    lesson = (
        await session.execute(select(Lesson).where(Lesson.number == corpo.lesson_number))
    ).scalar_one_or_none()
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aula não existe.")
    entry = NotebookEntry(
        user_id=usuario.id,
        lesson_id=lesson.id,
        kind=corpo.kind,
        content=corpo.content,
    )
    entry.lesson = lesson
    session.add(entry)
    await session.flush()
    if entry.kind == "favorite_phrase":
        await adicionar_item_revisao(
            session,
            usuario,
            lesson_id=lesson.id,
            item_type="phrase",
            source_type="notebook_entry",
            source_id=entry.id,
            source_key=f"notebook:{entry.id}",
            skill="speaking",
            prompt="Use esta frase em uma situação nova:",
            answer=entry.content,
            context="Crie uma frase parecida antes de revelar sua anotação.",
            origin_reason="Você marcou esta frase como favorita no caderno.",
            estimated_seconds=90,
        )
    await session.commit()
    await session.refresh(entry)
    return _entry_out(entry)


@router.put("/notebook/{entry_id}", response_model=NotebookEntryOut)
async def atualizar_anotacao(
    entry_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[NotebookEntryUpdate, Body()],
) -> NotebookEntryOut:
    entry = await _owned_entry(session, entry_id, usuario.id)
    entry.kind = corpo.kind
    entry.content = corpo.content
    entry.updated_at = datetime.now(UTC)
    if entry.kind == "favorite_phrase":
        await adicionar_item_revisao(
            session,
            usuario,
            lesson_id=entry.lesson_id,
            item_type="phrase",
            source_type="notebook_entry",
            source_id=entry.id,
            source_key=f"notebook:{entry.id}",
            skill="speaking",
            prompt="Use esta frase em uma situação nova:",
            answer=entry.content,
            context="Crie uma frase parecida antes de revelar sua anotação.",
            origin_reason="Você marcou esta frase como favorita no caderno.",
            estimated_seconds=90,
        )
    else:
        await remover_item_por_origem(session, usuario.id, f"notebook:{entry.id}")
    await session.commit()
    await session.refresh(entry)
    return _entry_out(entry)


@router.delete("/notebook/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_anotacao(
    entry_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    entry = await _owned_entry(session, entry_id, usuario.id)
    await remover_item_por_origem(session, usuario.id, f"notebook:{entry.id}")
    await session.delete(entry)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/export", response_model=PersonalDataExportOut)
async def exportar_dados(
    response: Response,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
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
            select(TranscriptionJob).where(TranscriptionJob.user_id == usuario.id)
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

    response.headers["Content-Disposition"] = 'attachment; filename="aulas-ingles-dados.json"'
    return PersonalDataExportOut(
        schema_version="1.3",
        exported_at=datetime.now(UTC),
        profile={
            "id": usuario.id,
            "email": usuario.email,
            "display_name": usuario.display_name,
            "created_at": usuario.created_at,
        },
        lesson_progress=[
            {"lesson_number": item.lesson.number, "studied_at": item.studied_at}
            for item in progress
        ],
        study_sessions=[
            {
                "lesson_number": lesson.number,
                "current_step": item.current_step,
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
                "weekly_minutes": plan.weekly_minutes,
                "preferred_days": plan.preferred_days,
                "goal": plan.goal,
                "created_at": plan.created_at,
                "updated_at": plan.updated_at,
            }
            if plan is not None
            else None
        ),
        step_progress=[
            {
                "lesson_number": lesson.number,
                "step": step.step,
                "seconds_spent": step.seconds_spent,
                "completed_at": step.completed_at,
                "updated_at": step.updated_at,
            }
            for step, _, lesson in step_rows
        ],
        skill_evidence=[
            {
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
                "lesson_number": lesson.number,
                "exercise_position": exercise.position,
                "answer": attempt.answer,
                "correct": attempt.correct,
                "created_at": attempt.created_at,
            }
            for attempt, exercise, lesson in attempt_rows
        ],
        review_items=[
            {
                "lesson_number": lesson.number,
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
                "lesson_number": lesson.number,
                "prompt_title": prompt.title,
                "draft": draft.text,
                "updated_at": draft.updated_at,
                "revisions": [
                    {
                        "version": revision.version,
                        "text": revision.text,
                        "created_at": revision.created_at,
                    }
                    for revision in draft.revisions
                ],
                "feedbacks": [
                    {
                        "text": feedback.text,
                        "word_count": feedback.word_count,
                        "sentence_count": feedback.sentence_count,
                        "ready": feedback.ready,
                        "checks": feedback.checks,
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
                "lesson_number": attempt.cue.media.lesson.number,
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
                "lesson_number": entry.lesson.number,
                "kind": entry.kind,
                "content": entry.content,
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
            }
            for entry in notebook
        ],
    )
