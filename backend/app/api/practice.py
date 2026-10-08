"""Laboratório de exercícios por aula, com retomada por conta."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.models import Exercise, Lesson, PracticeSession, PracticeSessionItem
from app.db.session import get_session
from app.schemas.lesson import ExerciseOut, exercise_public_payload
from app.schemas.practice import (
    ExerciseActivityType,
    ExerciseObjective,
    ExerciseSkill,
    PracticeHintOut,
    PracticePositionIn,
    PracticeRevealOut,
    PracticeSessionCreateIn,
    PracticeSessionOut,
)
from app.services.curriculum import lesson_by_course_number
from app.services.practice import (
    complete_session_if_ready,
    current_lesson_version,
    ensure_session_mutable,
    exercise_fingerprint,
    get_owned_practice_session,
    get_practice_item,
    practice_item_out,
    practice_session_out,
    session_content_changed,
)

router = APIRouter(tags=["practice"])


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


async def _lesson_or_404(session: AsyncSession, course_slug: str, number: int) -> Lesson:
    lesson = await lesson_by_course_number(session, course_slug, number)
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aula {number} não existe no curso {course_slug!r}.",
        )
    return lesson


def _same_request(practice: PracticeSession, body: PracticeSessionCreateIn) -> bool:
    return (
        practice.mode == body.mode
        and practice.activity_type == body.activity_type
        and practice.skill == body.skill
        and practice.objective == body.objective
        and practice.source_session_id == body.source_session_id
    )


async def _selected_exercises(
    session: AsyncSession,
    lesson_id: int,
    body: PracticeSessionCreateIn,
    user_id: int,
) -> list[Exercise]:
    stmt = select(Exercise).where(Exercise.lesson_id == lesson_id).order_by(Exercise.position)
    if body.activity_type is not None:
        stmt = stmt.where(Exercise.activity_type == body.activity_type)
    if body.skill is not None:
        stmt = stmt.where(Exercise.skill == body.skill)
    if body.objective is not None:
        stmt = stmt.where(Exercise.objective == body.objective)
    exercises = list((await session.execute(stmt)).scalars())

    if body.mode != "mistakes":
        if body.source_session_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="source_session_id só pode ser usado no modo mistakes.",
            )
        return exercises[:5] if body.mode == "quick" else exercises
    if body.source_session_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O modo mistakes exige source_session_id.",
        )
    source = await get_owned_practice_session(session, body.source_session_id, user_id)
    if source.lesson_id != lesson_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A sessão de origem pertence a outra aula.",
        )
    if source.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "practice_source_not_completed",
                "status": source.status,
            },
        )
    weak_ids = {
        item.exercise_id
        for item in source.items
        if item.first_try_correct is False or item.answer_revealed_at is not None
    }
    return [exercise for exercise in exercises if exercise.id in weak_ids]


@router.get(
    "/courses/{course_slug}/lessons/{number}/exercises",
    response_model=list[ExerciseOut],
)
async def list_lesson_exercises(
    course_slug: str,
    number: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    activity_type: Annotated[ExerciseActivityType | None, Query()] = None,
    skill: Annotated[ExerciseSkill | None, Query()] = None,
    objective: Annotated[ExerciseObjective | None, Query()] = None,
) -> list[ExerciseOut]:
    """Lista pública e filtrável; não publica dica, explicação nem gabarito."""
    lesson = await _lesson_or_404(session, course_slug, number)
    stmt = select(Exercise).where(Exercise.lesson_id == lesson.id).order_by(Exercise.position)
    if activity_type is not None:
        stmt = stmt.where(Exercise.activity_type == activity_type)
    if skill is not None:
        stmt = stmt.where(Exercise.skill == skill)
    if objective is not None:
        stmt = stmt.where(Exercise.objective == objective)
    exercises = list((await session.execute(stmt)).scalars())
    return [ExerciseOut.model_validate(exercise_public_payload(item)) for item in exercises]


@router.get(
    "/courses/{course_slug}/lessons/{number}/practice-sessions/active",
    response_model=PracticeSessionOut,
    responses={204: {"description": "Nenhuma sessão ativa."}},
)
async def get_active_practice_session(
    course_slug: str,
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> PracticeSessionOut | Response:
    _private(response)
    lesson = await _lesson_or_404(session, course_slug, number)
    practice = (
        await session.execute(
            select(PracticeSession).where(
                PracticeSession.user_id == usuario.id,
                PracticeSession.lesson_id == lesson.id,
                PracticeSession.status == "active",
            )
        )
    ).scalar_one_or_none()
    if practice is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return response
    return practice_session_out(practice)


@router.post(
    "/courses/{course_slug}/lessons/{number}/practice-sessions",
    response_model=PracticeSessionOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            "model": PracticeSessionOut,
            "description": "Sessão idempotente ou sessão ativa compatível retomada.",
        }
    },
)
async def create_practice_session(
    course_slug: str,
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    body: Annotated[PracticeSessionCreateIn, Body()],
    response: Response,
) -> PracticeSessionOut:
    _private(response)
    lesson = await _lesson_or_404(session, course_slug, number)
    key = str(body.idempotency_key)
    existing_key = (
        await session.execute(
            select(PracticeSession).where(
                PracticeSession.user_id == usuario.id,
                PracticeSession.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing_key is not None:
        if existing_key.lesson_id != lesson.id or not _same_request(existing_key, body):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A chave de idempotência já foi usada em outra sessão.",
            )
        response.status_code = status.HTTP_200_OK
        return practice_session_out(existing_key)

    active = (
        await session.execute(
            select(PracticeSession).where(
                PracticeSession.user_id == usuario.id,
                PracticeSession.lesson_id == lesson.id,
                PracticeSession.status == "active",
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        if session_content_changed(active):
            active.status = "abandoned"
            active.updated_at = datetime.now(UTC)
            await session.flush()
        elif _same_request(active, body):
            response.status_code = status.HTTP_200_OK
            return practice_session_out(active)
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "practice_session_active", "session_id": active.id},
            )

    exercises = await _selected_exercises(session, lesson.id, body, usuario.id)
    if not exercises:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nenhum exercício corresponde a esta sessão.",
        )
    practice = PracticeSession(
        user_id=usuario.id,
        lesson_id=lesson.id,
        source_session_id=body.source_session_id,
        idempotency_key=key,
        mode=body.mode,
        activity_type=body.activity_type,
        skill=body.skill,
        objective=body.objective,
        lesson_version=await current_lesson_version(session, lesson.id),
        content_fingerprint=exercise_fingerprint(exercises),
        total_items=len(exercises),
    )
    practice.items = [
        PracticeSessionItem(
            exercise_id=exercise.id,
            exercise=exercise,
            position=position,
            attempts=[],
        )
        for position, exercise in enumerate(exercises)
    ]
    session.add(practice)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Corrida de duas abas: a unicidade escolheu uma sessão; devolvemos-a.
        winner = (
            await session.execute(
                select(PracticeSession).where(
                    PracticeSession.user_id == usuario.id,
                    PracticeSession.lesson_id == lesson.id,
                    PracticeSession.status == "active",
                )
            )
        ).scalar_one_or_none()
        if winner is None or not _same_request(winner, body):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Outra sessão foi criada ao mesmo tempo.",
            ) from None
        response.status_code = status.HTTP_200_OK
        return practice_session_out(winner)
    return practice_session_out(practice)


@router.get("/practice-sessions/{session_id}", response_model=PracticeSessionOut)
async def get_practice_session(
    session_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> PracticeSessionOut:
    _private(response)
    return practice_session_out(await get_owned_practice_session(session, session_id, usuario.id))


@router.put("/practice-sessions/{session_id}/position", response_model=PracticeSessionOut)
async def update_practice_position(
    session_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    body: Annotated[PracticePositionIn, Body()],
    response: Response,
) -> PracticeSessionOut:
    _private(response)
    practice = await get_owned_practice_session(session, session_id, usuario.id, for_update=True)
    key = str(body.idempotency_key)
    if practice.last_state_key == key:
        if (
            practice.current_position != body.current_position
            or practice.state_revision != body.expected_revision + 1
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "practice_position_idempotency_mismatch"},
            )
        return practice_session_out(practice)
    ensure_session_mutable(practice)
    if body.expected_revision != practice.state_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "practice_revision_conflict",
                "current_revision": practice.state_revision,
            },
        )
    if body.current_position >= practice.total_items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A posição não existe nesta sessão.",
        )
    practice.current_position = body.current_position
    practice.state_revision += 1
    practice.last_state_key = key
    practice.updated_at = datetime.now(UTC)
    await session.commit()
    return practice_session_out(practice)


@router.post(
    "/practice-sessions/{session_id}/items/{exercise_id}/hints/{level}",
    response_model=PracticeHintOut,
)
async def open_practice_hint(
    session_id: int,
    exercise_id: int,
    level: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> PracticeHintOut:
    _private(response)
    practice = await get_owned_practice_session(session, session_id, usuario.id, for_update=True)
    ensure_session_mutable(practice)
    item = get_practice_item(practice, exercise_id)
    hint = next((candidate for candidate in item.exercise.hints if candidate.level == level), None)
    if hint is None:
        raise HTTPException(status_code=404, detail="Dica não existe.")
    if level > item.highest_hint_level + 1:
        raise HTTPException(status_code=409, detail="Abra as dicas anteriores primeiro.")
    if level > 1 and item.first_try_correct is not False:
        raise HTTPException(
            status_code=409,
            detail="Faça uma tentativa incorreta nesta sessão antes de abrir esta dica.",
        )
    item.highest_hint_level = max(item.highest_hint_level, level)
    practice.updated_at = datetime.now(UTC)
    await session.commit()
    return PracticeHintOut(
        level=hint.level,
        content=hint.content,
        item=practice_item_out(item),
    )


@router.post(
    "/practice-sessions/{session_id}/items/{exercise_id}/reveal",
    response_model=PracticeRevealOut,
)
async def reveal_practice_answer(
    session_id: int,
    exercise_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> PracticeRevealOut:
    _private(response)
    practice = await get_owned_practice_session(session, session_id, usuario.id, for_update=True)
    if session_content_changed(practice):
        ensure_session_mutable(practice)
    item = get_practice_item(practice, exercise_id)
    if item.answer_revealed_at is None:
        ensure_session_mutable(practice)
        now = datetime.now(UTC)
        item.answer_revealed_at = now
        item.completed_at = item.completed_at or now
        practice.updated_at = now
        complete_session_if_ready(practice)
        await session.commit()
    return PracticeRevealOut(
        answers=[answer.value for answer in item.exercise.answers],
        explanation=item.exercise.explanation,
        item=practice_item_out(item),
    )
