"""Fila de revisão multimodal com agendamento adaptado ao tipo."""

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import Row, Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.concurrency import conflict, require_idempotency_key, require_revision
from app.api.deps import UsuarioAtual
from app.api.errors import IDEMPOTENT_WRITE_RESPONSES
from app.db.models import Course, CourseUnit, Lesson, ReviewEvent, ReviewItem, User, VocabItem
from app.db.session import get_session
from app.domain.sm2 import Estado, revisar
from app.pagination import (
    PAGE_LIMIT_MAX,
    PAGINATED_ALTERNATIVE_HEADER,
    InvalidCursor,
    decode_time_id_cursor,
    encode_time_id_cursor,
)
from app.schemas.review import (
    CardOut,
    DeckSummaryOut,
    GradeIn,
    GradeOut,
    ReviewItemPageOut,
    ReviewItemStatus,
    ReviewItemStatusIn,
    ReviewItemType,
)
from app.services.curriculum import DEFAULT_COURSE_SLUG, lesson_by_course_number
from app.services.publication import lock_publication, published_lesson_ids
from app.services.review import adicionar_cartas

router = APIRouter(prefix="/review", tags=["review"])

TYPE_INTERVAL_FACTOR = {
    "vocabulary": 1.0,
    "phrase": 1.1,
    "grammar_error": 0.8,
    "listening": 0.8,
    "writing_prompt": 1.3,
    "speaking_prompt": 1.2,
}


def _reason_values(
    origin_reason: str,
    last_reviewed_at: datetime | None,
    lapses: int,
    interval_days: int,
) -> str:
    if last_reviewed_at is None:
        return f"{origin_reason} É a primeira revisão deste item."
    if lapses:
        label = "tropeço" if lapses == 1 else "tropeços"
        return f"{origin_reason} Ele voltou após {lapses} {label} no histórico."
    label = "dia" if interval_days == 1 else "dias"
    return f"{origin_reason} O intervalo atual de {interval_days} {label} venceu."


def _reason(item: ReviewItem) -> str:
    return _reason_values(
        item.origin_reason,
        item.last_reviewed_at,
        item.lapses,
        item.interval_days,
    )


def _out(item: ReviewItem) -> CardOut:
    return CardOut(
        id=item.id,
        revision=item.revision,
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


def _recorte[*Cols](query: Select[*Cols], *, course: str | None, unit: str | None) -> Select[*Cols]:
    """Recorte de curso e unidade — o mesmo na lista legada e na página."""
    if course is not None:
        query = query.where(Course.slug == course)
    if unit is not None:
        query = query.where(CourseUnit.slug == unit)
    return query


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
    return _recorte(query, course=course, unit=unit)


def _item_page_query(
    user_id: int,
    *,
    item_status: ReviewItemStatus,
    course: str | None,
    unit: str | None,
) -> Select[*tuple[Any, ...]]:
    query = (
        select(
            ReviewItem.id,
            ReviewItem.revision,
            ReviewItem.item_type,
            ReviewItem.skill,
            ReviewItem.prompt,
            ReviewItem.prompt_note,
            ReviewItem.answer,
            ReviewItem.context,
            Course.slug.label("course_slug"),
            Course.title.label("course_title"),
            CourseUnit.slug.label("unit_slug"),
            Lesson.number.label("lesson_number"),
            Lesson.title.label("lesson_title"),
            ReviewItem.origin_reason,
            ReviewItem.last_reviewed_at,
            ReviewItem.estimated_seconds,
            ReviewItem.media_url,
            ReviewItem.cue_start_seconds,
            ReviewItem.cue_end_seconds,
            ReviewItem.status,
            ReviewItem.vocab_item_id,
            ReviewItem.ease_factor,
            ReviewItem.interval_days,
            ReviewItem.repetitions,
            ReviewItem.lapses,
            ReviewItem.due_at,
            ReviewItem.created_at,
        )
        .join(Lesson, ReviewItem.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            ReviewItem.user_id == user_id,
            ReviewItem.status == item_status,
        )
    )
    return _recorte(query, course=course, unit=unit)


def _page_item_out(row: Row[*tuple[Any, ...]]) -> CardOut:
    return CardOut(
        id=row.id,
        revision=row.revision,
        item_type=cast(ReviewItemType, row.item_type),
        skill=row.skill,
        prompt=row.prompt,
        prompt_note=row.prompt_note,
        answer=row.answer,
        context=row.context,
        course_slug=row.course_slug,
        course_title=row.course_title,
        unit_slug=row.unit_slug,
        lesson_number=row.lesson_number,
        lesson_title=row.lesson_title,
        reason=_reason_values(
            row.origin_reason,
            row.last_reviewed_at,
            row.lapses,
            row.interval_days,
        ),
        estimated_seconds=row.estimated_seconds,
        media_url=row.media_url,
        cue_start_seconds=row.cue_start_seconds,
        cue_end_seconds=row.cue_end_seconds,
        status=cast(ReviewItemStatus, row.status),
        vocab_item_id=row.vocab_item_id,
        ease_factor=row.ease_factor,
        interval_days=row.interval_days,
        repetitions=row.repetitions,
        lapses=row.lapses,
        due_at=row.due_at,
    )


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
    response: Response,
    item_status: Annotated[ReviewItemStatus, Query(alias="status")] = "suspended",
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)] = PAGE_LIMIT_MAX,
) -> list[CardOut]:
    """Lista legada com teto: devolve só a primeira página; o histórico completo vive em /page."""
    response.headers[PAGINATED_ALTERNATIVE_HEADER] = "/api/review/items/page"
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
            )
            .order_by(ReviewItem.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return [_out(item) for item in items]


@router.get("/items/page", response_model=ReviewItemPageOut)
async def listar_itens_paginados(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    item_status: Annotated[ReviewItemStatus, Query(alias="status")] = "suspended",
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> ReviewItemPageOut:
    boundary = None
    if cursor is not None:
        try:
            boundary = decode_time_id_cursor(cursor)
        except InvalidCursor as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_cursor", "message": "Cursor de paginação inválido."},
            ) from error
    query = _item_page_query(
        usuario.id,
        item_status=item_status,
        course=course,
        unit=unit,
    )
    if boundary is not None:
        query = query.where(
            tuple_(ReviewItem.created_at, ReviewItem.id)
            < tuple_(boundary.timestamp, boundary.row_id)
        )
    rows = (
        await session.execute(
            query.order_by(ReviewItem.created_at.desc(), ReviewItem.id.desc()).limit(limit + 1)
        )
    ).all()
    page = rows[:limit]
    return ReviewItemPageOut(
        items=[_page_item_out(row) for row in page],
        next_cursor=(
            encode_time_id_cursor(page[-1].created_at, page[-1].id)
            if len(rows) > limit and page
            else None
        ),
    )


async def _owned_item(session: AsyncSession, item_id: int, user_id: int) -> ReviewItem:
    item = (
        await session.execute(
            select(ReviewItem)
            .where(ReviewItem.id == item_id, ReviewItem.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não existe.")
    return item


@router.post("/{item_id}/grade", response_model=GradeOut, responses=IDEMPOTENT_WRITE_RESPONSES)
async def avaliar(
    item_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[GradeIn, Body()],
) -> GradeOut:
    require_revision(corpo.expected_revision)
    require_idempotency_key(corpo.idempotency_key)
    key = str(corpo.idempotency_key or uuid4())
    fingerprint = sha256(
        json.dumps([item_id, corpo.quality, corpo.expected_revision]).encode()
    ).hexdigest()
    # Serializa chaves por conta, inclusive a mesma chave enviada para dois itens.
    # Advisory lock não altera a conta e não conflita com locks FK de suas dependentes.
    await session.execute(select(func.pg_advisory_xact_lock(3801, usuario.id)))
    previous = (
        await session.execute(
            select(ReviewEvent).where(
                ReviewEvent.user_id == usuario.id,
                ReviewEvent.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()
    if previous is not None:
        if previous.fingerprint != fingerprint:
            raise conflict("idempotency_key_reused", {})
        return GradeOut.model_validate(previous.after_state)
    item = await _owned_item(session, item_id, usuario.id)
    if corpo.expected_revision is not None and corpo.expected_revision != item.revision:
        raise conflict("review_revision_conflict", {"id": item.id, "revision": item.revision})
    if item.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Item suspenso.")

    before = _grade_out(item).model_dump(mode="json")
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
    item.revision += 1
    result = _grade_out(item)
    session.add(
        ReviewEvent(
            user_id=usuario.id,
            item_id=item.id,
            idempotency_key=key,
            fingerprint=fingerprint,
            quality=corpo.quality,
            algorithm_version="sm2-multimodal-v1",
            before_state=before,
            after_state=result.model_dump(mode="json"),
        )
    )
    await session.commit()
    return result


def _grade_out(item: ReviewItem) -> GradeOut:
    return GradeOut(
        id=item.id,
        revision=item.revision,
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
    if item.status != corpo.status:
        item.revision += 1
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
    await lock_publication(session)
    item = (
        await session.execute(
            select(VocabItem).where(
                VocabItem.id == vocab_item_id,
                VocabItem.lesson_id.in_(published_lesson_ids()),
            )
        )
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
