"""Caderno e portabilidade dos dados do aluno."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.api.review import adicionar_item_revisao, remover_item_por_origem
from app.db.models import (
    Course,
    CourseUnit,
    Lesson,
    NotebookEntry,
)
from app.db.session import get_session
from app.pagination import (
    PAGE_LIMIT_MAX,
    PAGINATED_ALTERNATIVE_HEADER,
    InvalidCursor,
    decode_time_id_cursor,
    encode_time_id_cursor,
)
from app.schemas.notebook import (
    AccountDeletionIn,
    AccountDeletionOut,
    NotebookEntryIn,
    NotebookEntryOut,
    NotebookEntryUpdate,
    NotebookKind,
    NotebookPageOut,
    PersonalDataExportOut,
)
from app.services.curriculum import DEFAULT_COURSE_SLUG, lesson_by_course_number

router = APIRouter(prefix="/me", tags=["me"])


def _entry_out(entry: NotebookEntry) -> NotebookEntryOut:
    return NotebookEntryOut(
        id=entry.id,
        course_slug=entry.lesson.course.slug,
        course_title=entry.lesson.course.title,
        unit_slug=entry.lesson.unit.slug,
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
    response: Response,
    lesson: Annotated[int | None, Query(ge=1)] = None,
    kind: Annotated[NotebookKind | None, Query()] = None,
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)] = PAGE_LIMIT_MAX,
) -> list[NotebookEntryOut]:
    """Lista legada com teto: devolve só a primeira página; o histórico completo vive em /page."""
    response.headers[PAGINATED_ALTERNATIVE_HEADER] = "/api/me/notebook/page"
    query = select(NotebookEntry).where(NotebookEntry.user_id == usuario.id)
    if course is not None:
        query = query.where(NotebookEntry.lesson.has(Lesson.course.has(Course.slug == course)))
    if unit is not None:
        query = query.where(NotebookEntry.lesson.has(Lesson.unit.has(CourseUnit.slug == unit)))
    if lesson is not None:
        query = query.where(
            NotebookEntry.lesson.has(
                and_(
                    Lesson.number == lesson,
                    Lesson.course.has(slug=course or DEFAULT_COURSE_SLUG),
                )
            )
        )
    if kind is not None:
        query = query.where(NotebookEntry.kind == kind)
    entries = (
        await session.execute(query.order_by(NotebookEntry.updated_at.desc()).limit(limit))
    ).scalars()
    return [_entry_out(entry) for entry in entries]


@router.get("/notebook/page", response_model=NotebookPageOut)
async def listar_caderno_paginado(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    lesson: Annotated[int | None, Query(ge=1)] = None,
    kind: Annotated[NotebookKind | None, Query()] = None,
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> NotebookPageOut:
    """Keyset page ordered by the same update recency shown in the UI."""
    query = (
        select(
            NotebookEntry.id,
            Course.slug.label("course_slug"),
            Course.title.label("course_title"),
            CourseUnit.slug.label("unit_slug"),
            Lesson.number.label("lesson_number"),
            Lesson.title.label("lesson_title"),
            NotebookEntry.kind,
            NotebookEntry.content,
            NotebookEntry.created_at,
            NotebookEntry.updated_at,
        )
        .join(Lesson, NotebookEntry.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(NotebookEntry.user_id == usuario.id)
    )
    if course is not None:
        query = query.where(Course.slug == course)
    if unit is not None:
        query = query.where(CourseUnit.slug == unit)
    if lesson is not None:
        query = query.where(
            Lesson.number == lesson,
            Course.slug == (course or DEFAULT_COURSE_SLUG),
        )
    if kind is not None:
        query = query.where(NotebookEntry.kind == kind)
    if cursor is not None:
        try:
            boundary = decode_time_id_cursor(cursor)
        except InvalidCursor as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_cursor", "message": "Cursor de paginação inválido."},
            ) from error
        query = query.where(
            tuple_(NotebookEntry.updated_at, NotebookEntry.id)
            < tuple_(boundary.timestamp, boundary.row_id)
        )
    rows = (
        await session.execute(
            query.order_by(NotebookEntry.updated_at.desc(), NotebookEntry.id.desc()).limit(
                limit + 1
            )
        )
    ).all()
    page_rows = rows[:limit]
    items = [NotebookEntryOut.model_validate(row._mapping) for row in page_rows]
    next_cursor = None
    if len(rows) > limit and page_rows:
        last = page_rows[-1]
        next_cursor = encode_time_id_cursor(last.updated_at, last.id)
    return NotebookPageOut(items=items, next_cursor=next_cursor)


@router.post("/notebook", response_model=NotebookEntryOut, status_code=status.HTTP_201_CREATED)
async def criar_anotacao(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[NotebookEntryIn, Body()],
) -> NotebookEntryOut:
    lesson = await lesson_by_course_number(session, corpo.course_slug, corpo.lesson_number)
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
    from app.services.personal_export import export_personal_data

    # A autenticação abriu uma transação de leitura; o serviço inicia um novo
    # snapshot e relê o perfil, sem reter uma segunda conexão do pool.
    user_id = usuario.id
    await session.rollback()
    data = await export_personal_data(session, user_id)
    response.headers["Content-Disposition"] = 'attachment; filename="aulas-ingles-dados.json"'
    response.headers["Cache-Control"] = "no-store"
    return data


@router.delete(
    "/account",
    response_model=AccountDeletionOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def excluir_conta(
    corpo: Annotated[AccountDeletionIn, Body()],
    response: Response,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccountDeletionOut:
    from app.api.auth import COOKIE
    from app.core.config import get_settings
    from app.services.account_deletion import delete_account

    result = await delete_account(session, usuario.id, usuario.password_hash, corpo)
    response.delete_cookie(
        COOKIE,
        path="/api/auth",
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return result
