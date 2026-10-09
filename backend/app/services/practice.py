"""Regras compartilhadas da sessão de exercícios.

O fingerprint fica exclusivamente no servidor: além de detectar alterações,
isso evita transformar respostas curtas em um hash público fácil de enumerar.
"""

import hashlib
import json
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Exercise,
    LessonVersion,
    PracticeSession,
    PracticeSessionItem,
)
from app.domain.answers import analisar_resposta
from app.schemas.lesson import ExerciseOut, exercise_public_payload
from app.schemas.practice import (
    PracticeSessionItemOut,
    PracticeSessionOut,
    PracticeSummaryOut,
)
from app.schemas.progress import (
    AttemptFeedbackOut,
    ExerciseHintOut,
    FeedbackTokenOut,
    PracticeAttemptStateOut,
)


def exercise_fingerprint(exercises: list[Exercise]) -> str:
    """Versão determinística do conteúdo que afeta apresentação ou correção."""
    payload = [
        {
            "id": exercise.id,
            "position": exercise.position,
            "activity_type": exercise.activity_type,
            "skill": exercise.skill,
            "objective": exercise.objective,
            "options": exercise.options,
            "classification_items": exercise.classification_items,
            "classification_categories": exercise.classification_categories,
            "prompt": exercise.prompt,
            "hint": exercise.hint,
            "explanation": exercise.explanation,
            "answers": [answer.value for answer in exercise.answers],
            "hints": [{"level": hint.level, "content": hint.content} for hint in exercise.hints],
        }
        for exercise in exercises
    ]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def current_lesson_version(session: AsyncSession, lesson_id: int) -> int:
    value = (
        await session.execute(
            select(func.max(LessonVersion.version)).where(LessonVersion.lesson_id == lesson_id)
        )
    ).scalar_one()
    return int(value or 1)


async def get_owned_practice_session(
    session: AsyncSession,
    session_id: int,
    user_id: int,
    *,
    for_update: bool = False,
) -> PracticeSession:
    statement = select(PracticeSession).where(
        PracticeSession.id == session_id,
        PracticeSession.user_id == user_id,
    )
    if for_update:
        # Todas as mutações de uma sessão passam pelo mesmo lock. Isso evita
        # perder contadores e também torna a revisão de posição um CAS real.
        statement = statement.with_for_update(of=PracticeSession)
    practice = (await session.execute(statement)).scalar_one_or_none()
    if practice is None:
        # 404 não confirma a existência de uma sessão pertencente a outra conta.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão de exercícios não existe.",
        )
    return practice


def ensure_session_content_current(practice: PracticeSession) -> None:
    if session_content_changed(practice):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "practice_content_changed",
                "session_id": practice.id,
                "content_version": practice.lesson_version,
            },
        )


def _current_selection(practice: PracticeSession) -> list[Exercise]:
    """Reconstrói a seleção para detectar também itens incluídos ou removidos."""
    if practice.mode == "mistakes":
        # A repetição é uma fotografia dos erros da sessão de origem; novos
        # erros não entram retroativamente, mas o conteúdo de cada item conta.
        return [item.exercise for item in practice.items]
    exercises = [
        exercise
        for exercise in practice.lesson.exercises
        if (practice.activity_type is None or exercise.activity_type == practice.activity_type)
        and (practice.skill is None or exercise.skill == practice.skill)
        and (practice.objective is None or exercise.objective == practice.objective)
    ]
    return exercises[:5] if practice.mode == "quick" else exercises


def session_content_changed(practice: PracticeSession) -> bool:
    return exercise_fingerprint(_current_selection(practice)) != practice.content_fingerprint


def ensure_session_mutable(practice: PracticeSession) -> None:
    if practice.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "practice_session_not_active", "status": practice.status},
        )
    ensure_session_content_current(practice)


def get_practice_item(practice: PracticeSession, exercise_id: int) -> PracticeSessionItem:
    item = next(
        (candidate for candidate in practice.items if candidate.exercise_id == exercise_id),
        None,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O exercício não pertence a esta sessão.",
        )
    return item


def item_outcome(item: PracticeSessionItem) -> str:
    if item.answer_revealed_at is not None:
        return "revealed"
    if item.completed_at is None:
        return "pending"
    return "first_try_correct" if item.first_try_correct else "corrected"


def _feedback(item: PracticeSessionItem) -> AttemptFeedbackOut | None:
    if not item.attempts:
        return None
    attempt = item.attempts[-1]
    feedback = analisar_resposta(attempt.answer, [answer.value for answer in item.exercise.answers])
    return AttemptFeedbackOut(
        category=feedback.category,
        message=feedback.message,
        tokens=[
            FeedbackTokenOut(text=token.text, status=token.status) for token in feedback.tokens
        ],
    )


def practice_item_out(
    item: PracticeSessionItem, *, content_changed: bool = False
) -> PracticeSessionItemOut:
    revealed = item.answer_revealed_at is not None
    completed_by_answer = item.completed_at is not None and not revealed
    hints = [] if content_changed else item.exercise.hints[: item.highest_hint_level]
    return PracticeSessionItemOut(
        position=item.position,
        exercise=ExerciseOut.model_validate(exercise_public_payload(item.exercise)),
        attempt_count=item.attempt_count,
        first_try_correct=item.first_try_correct,
        highest_hint_level=item.highest_hint_level,
        opened_hints=[ExerciseHintOut(level=hint.level, content=hint.content) for hint in hints],
        answer_revealed=revealed,
        completed_at=item.completed_at,
        outcome=item_outcome(item),  # type: ignore[arg-type]
        last_feedback=None if content_changed else _feedback(item),
        answers=(
            [answer.value for answer in item.exercise.answers]
            if revealed and not content_changed
            else None
        ),
        explanation=(
            item.exercise.explanation
            if (revealed or completed_by_answer) and not content_changed
            else None
        ),
    )


def practice_summary(practice: PracticeSession) -> PracticeSummaryOut:
    outcomes = [item_outcome(item) for item in practice.items]
    return PracticeSummaryOut(
        total=len(outcomes),
        completed=sum(outcome != "pending" for outcome in outcomes),
        first_try_correct=outcomes.count("first_try_correct"),
        corrected=outcomes.count("corrected"),
        revealed=outcomes.count("revealed"),
        pending=outcomes.count("pending"),
    )


def practice_session_out(practice: PracticeSession) -> PracticeSessionOut:
    changed = session_content_changed(practice)
    return PracticeSessionOut(
        id=practice.id,
        course_slug=practice.lesson.course_slug,
        unit_slug=practice.lesson.unit_slug,
        lesson_number=practice.lesson.number,
        lesson_title=practice.lesson.title,
        content_version=practice.lesson_version,
        mode=practice.mode,  # type: ignore[arg-type]
        status=practice.status,  # type: ignore[arg-type]
        activity_type=practice.activity_type,
        skill=practice.skill,
        objective=practice.objective,  # type: ignore[arg-type]
        content_changed=changed,
        current_position=practice.current_position,
        state_revision=practice.state_revision,
        started_at=practice.started_at,
        updated_at=practice.updated_at,
        completed_at=practice.completed_at,
        summary=practice_summary(practice),
        items=[practice_item_out(item, content_changed=changed) for item in practice.items],
    )


def practice_attempt_state(
    practice: PracticeSession, item: PracticeSessionItem
) -> PracticeAttemptStateOut:
    return PracticeAttemptStateOut(
        session_id=practice.id,
        item_position=item.position,
        attempt_count=item.attempt_count,
        first_try_correct=item.first_try_correct,
        outcome=item_outcome(item),  # type: ignore[arg-type]
        completed_at=item.completed_at,
        session_status=practice.status,  # type: ignore[arg-type]
    )


def complete_session_if_ready(practice: PracticeSession) -> None:
    if practice.status == "active" and all(
        item.completed_at is not None for item in practice.items
    ):
        now = datetime.now(UTC)
        practice.status = "completed"
        practice.completed_at = now
        practice.updated_at = now
