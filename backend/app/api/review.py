"""Fila de revisão multimodal com agendamento adaptado ao tipo."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.models import Course, CourseUnit, Lesson, ReviewItem, User, VocabItem
from app.db.session import get_session
from app.domain.sm2 import Estado, revisar
from app.schemas.review import (
    CardOut,
    DeckSummaryOut,
    GradeIn,
    GradeOut,
    ReviewItemStatus,
    ReviewItemStatusIn,
    ReviewItemType,
)
from app.services.curriculum import DEFAULT_COURSE_SLUG, lesson_by_course_number

router = APIRouter(prefix="/review", tags=["review"])

TYPE_INTERVAL_FACTOR = {
    "vocabulary": 1.0,
    "phrase": 1.1,
    "grammar_error": 0.8,
    "listening": 0.8,
    "writing_prompt": 1.3,
    "speaking_prompt": 1.2,
}


async def adicionar_item_revisao(
    session: AsyncSession,
    usuario: User,
    *,
    lesson_id: int,
    item_type: ReviewItemType,
    source_type: str,
    source_id: int,
    source_key: str,
    skill: str,
    prompt: str,
    answer: str,
    origin_reason: str,
    estimated_seconds: int,
    prompt_note: str | None = None,
    context: str | None = None,
    vocab_item_id: int | None = None,
    media_url: str | None = None,
    cue_start_seconds: float | None = None,
    cue_end_seconds: float | None = None,
) -> bool:
    """Cria uma origem uma vez; novos erros atualizam o conteúdo sem duplicar."""
    item = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.user_id == usuario.id,
                ReviewItem.source_key == source_key,
            )
        )
    ).scalar_one_or_none()
    if item is not None:
        item.prompt = prompt
        item.prompt_note = prompt_note
        item.answer = answer
        item.context = context
        item.origin_reason = origin_reason
        item.media_url = media_url
        item.cue_start_seconds = cue_start_seconds
        item.cue_end_seconds = cue_end_seconds
        return False

    session.add(
        ReviewItem(
            user_id=usuario.id,
            lesson_id=lesson_id,
            vocab_item_id=vocab_item_id,
            item_type=item_type,
            source_type=source_type,
            source_id=source_id,
            source_key=source_key,
            skill=skill,
            prompt=prompt,
            prompt_note=prompt_note,
            answer=answer,
            context=context,
            origin_reason=origin_reason,
            media_url=media_url,
            cue_start_seconds=cue_start_seconds,
            cue_end_seconds=cue_end_seconds,
            estimated_seconds=estimated_seconds,
            due_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return True


async def remover_item_por_origem(session: AsyncSession, user_id: int, source_key: str) -> None:
    item = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.user_id == user_id,
                ReviewItem.source_key == source_key,
            )
        )
    ).scalar_one_or_none()
    if item is not None:
        await session.delete(item)


async def adicionar_cartas(session: AsyncSession, usuario: User, itens: list[VocabItem]) -> int:
    """Compatibilidade do deck: vocabulário agora entra na fila generalizada."""
    novas = 0
    for item in itens:
        novas += int(
            await adicionar_item_revisao(
                session,
                usuario,
                lesson_id=item.lesson_id,
                item_type="vocabulary",
                source_type="vocab_item",
                source_id=item.id,
                source_key=f"vocab:{item.id}",
                skill="vocabulary",
                prompt=item.term,
                prompt_note=item.ipa,
                answer=item.translation_pt,
                context=item.example_en,
                origin_reason="Vocabulário incluído no seu deck de estudo.",
                estimated_seconds=45,
                vocab_item_id=item.id,
            )
        )
    return novas


def _reason(item: ReviewItem) -> str:
    if item.last_reviewed_at is None:
        return f"{item.origin_reason} É a primeira revisão deste item."
    if item.lapses:
        label = "tropeço" if item.lapses == 1 else "tropeços"
        return f"{item.origin_reason} Ele voltou após {item.lapses} {label} no histórico."
    label = "dia" if item.interval_days == 1 else "dias"
    return f"{item.origin_reason} O intervalo atual de {item.interval_days} {label} venceu."


def _out(item: ReviewItem) -> CardOut:
    return CardOut(
        id=item.id,
        item_type=cast(ReviewItemType, item.item_type),
        skill=item.skill,
        prompt=item.prompt,
        prompt_note=item.prompt_note,
        answer=item.answer,
        context=item.context,
        course_slug=item.lesson.course.slug,
        course_title=item.lesson.course.title,
        unit_slug=item.lesson.unit.slug,
        lesson_number=item.lesson.number,
        lesson_title=item.lesson.title,
        reason=_reason(item),
        estimated_seconds=item.estimated_seconds,
        media_url=item.media_url,
        cue_start_seconds=item.cue_start_seconds,
        cue_end_seconds=item.cue_end_seconds,
        status=cast(ReviewItemStatus, item.status),
        vocab_item_id=item.vocab_item_id,
        ease_factor=item.ease_factor,
        interval_days=item.interval_days,
        repetitions=item.repetitions,
        lapses=item.lapses,
        due_at=item.due_at,
    )


async def _resumo(session: AsyncSession, usuario: User, criadas: int = 0) -> DeckSummaryOut:
    now = datetime.now(UTC)
    total = (
        await session.execute(
            select(func.count()).select_from(ReviewItem).where(ReviewItem.user_id == usuario.id)
        )
    ).scalar_one()
    due = (
        await session.execute(
            select(func.count())
            .select_from(ReviewItem)
            .where(
                ReviewItem.user_id == usuario.id,
                ReviewItem.status == "active",
                ReviewItem.due_at <= now,
            )
        )
    ).scalar_one()
    suspended = (
        await session.execute(
            select(func.count())
            .select_from(ReviewItem)
            .where(ReviewItem.user_id == usuario.id, ReviewItem.status == "suspended")
        )
    ).scalar_one()
    grouped = (
        await session.execute(
            select(ReviewItem.item_type, func.count(ReviewItem.id))
            .where(ReviewItem.user_id == usuario.id)
            .group_by(ReviewItem.item_type)
        )
    ).all()
    return DeckSummaryOut(
        due_now=due,
        total_cards=total,
        suspended=suspended,
        by_type={item_type: count for item_type, count in grouped},
        added=criadas,
    )


@router.get("/summary", response_model=DeckSummaryOut)
async def resumo(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeckSummaryOut:
    return await _resumo(session, usuario)


def _filtered_query(
    user_id: int,
    *,
    item_status: ReviewItemStatus,
    item_type: ReviewItemType | None,
    skill: str | None,
    max_minutes: int | None,
    course: str | None,
    unit: str | None,
    due_only: bool,
) -> Select[ReviewItem]:
    query = (
        select(ReviewItem)
        .join(Lesson, ReviewItem.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            ReviewItem.user_id == user_id,
            ReviewItem.status == item_status,
        )
    )
    if due_only:
        query = query.where(ReviewItem.due_at <= datetime.now(UTC))
    if item_type is not None:
        query = query.where(ReviewItem.item_type == item_type)
    if skill is not None:
        query = query.where(ReviewItem.skill == skill)
    if max_minutes is not None:
        query = query.where(ReviewItem.estimated_seconds <= max_minutes * 60)
    if course is not None:
        query = query.where(Course.slug == course)
    if unit is not None:
        query = query.where(CourseUnit.slug == unit)
    return query


@router.get("/due", response_model=list[CardOut])
async def vencidas(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    item_type: Annotated[ReviewItemType | None, Query()] = None,
    skill: Annotated[str | None, Query(max_length=40)] = None,
    max_minutes: Annotated[int | None, Query(ge=1, le=30)] = None,
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
) -> list[CardOut]:
    items = (
        await session.execute(
            _filtered_query(
                usuario.id,
                item_status="active",
                item_type=item_type,
                skill=skill,
                max_minutes=max_minutes,
                course=course,
                unit=unit,
                due_only=True,
            )
            .order_by(ReviewItem.due_at, ReviewItem.id)
            .limit(limit)
        )
    ).scalars()
    return [_out(item) for item in items]


@router.get("/items", response_model=list[CardOut])
async def listar_itens(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    item_status: Annotated[ReviewItemStatus, Query(alias="status")] = "suspended",
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
) -> list[CardOut]:
    items = (
        await session.execute(
            _filtered_query(
                usuario.id,
                item_status=item_status,
                item_type=None,
                skill=None,
                max_minutes=None,
                course=course,
                unit=unit,
                due_only=False,
            ).order_by(ReviewItem.created_at.desc())
        )
    ).scalars()
    return [_out(item) for item in items]


async def _owned_item(session: AsyncSession, item_id: int, user_id: int) -> ReviewItem:
    item = (
        await session.execute(
            select(ReviewItem).where(ReviewItem.id == item_id, ReviewItem.user_id == user_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não existe.")
    return item


@router.post("/{item_id}/grade", response_model=GradeOut)
async def avaliar(
    item_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[GradeIn, Body()],
) -> GradeOut:
    item = await _owned_item(session, item_id, usuario.id)
    if item.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Item suspenso.")

    now = datetime.now(UTC)
    base, _ = revisar(
        Estado(
            ease_factor=item.ease_factor,
            interval_days=item.interval_days,
            repetitions=item.repetitions,
            lapses=item.lapses,
        ),
        corpo.quality,
        now,
    )
    factor = TYPE_INTERVAL_FACTOR[item.item_type]
    interval = max(1, round(base.interval_days * factor))
    item.ease_factor = base.ease_factor
    item.interval_days = interval
    item.repetitions = base.repetitions
    item.lapses = base.lapses
    item.due_at = now + timedelta(days=interval)
    item.last_reviewed_at = now
    await session.commit()

    return GradeOut(
        id=item.id,
        interval_days=item.interval_days,
        ease_factor=item.ease_factor,
        repetitions=item.repetitions,
        lapses=item.lapses,
        due_at=item.due_at,
    )


@router.patch("/{item_id}", response_model=CardOut)
async def alterar_status(
    item_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[ReviewItemStatusIn, Body()],
) -> CardOut:
    item = await _owned_item(session, item_id, usuario.id)
    item.status = corpo.status
    item.suspended_at = datetime.now(UTC) if corpo.status == "suspended" else None
    await session.commit()
    await session.refresh(item)
    return _out(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_item(
    item_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    item = await _owned_item(session, item_id, usuario.id)
    await session.delete(item)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/items/{vocab_item_id}", response_model=DeckSummaryOut)
async def adicionar_item(
    vocab_item_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeckSummaryOut:
    item = (
        await session.execute(select(VocabItem).where(VocabItem.id == vocab_item_id))
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não existe.")
    created = await adicionar_cartas(session, usuario, [item])
    await session.commit()
    return await _resumo(session, usuario, created)


@router.post("/lessons/{number}", response_model=DeckSummaryOut)
async def adicionar_aula(
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeckSummaryOut:
    lesson = await lesson_by_course_number(session, DEFAULT_COURSE_SLUG, number)
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aula não existe.")
    created = await adicionar_cartas(session, usuario, list(lesson.vocab))
    await session.commit()
    return await _resumo(session, usuario, created)
