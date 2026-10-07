"""Leitura do conteúdo das aulas. Tudo público nesta sprint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson, VocabItem
from app.db.session import get_session
from app.schemas.lesson import (
    LessonDetailOut,
    LessonSummaryOut,
    VocabItemOut,
    VocabItemWithLessonOut,
)

router = APIRouter(tags=["lessons"])


@router.get("/lessons", response_model=list[LessonSummaryOut])
async def listar_aulas(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Lesson]:
    """Todas as aulas, em ordem, com o mínimo para montar a navegação."""
    result = await session.execute(select(Lesson).order_by(Lesson.number))
    return list(result.scalars())


@router.get("/lessons/{number}", response_model=LessonDetailOut)
async def obter_aula(
    number: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Lesson:
    """Uma aula inteira: gramática, frases, vocabulário, pronúncia e exercícios."""
    lesson = (
        await session.execute(select(Lesson).where(Lesson.number == number))
    ).scalar_one_or_none()
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Aula {number} não existe."
        )
    return lesson


@router.get("/vocab", response_model=list[VocabItemWithLessonOut])
async def listar_vocabulario(
    session: Annotated[AsyncSession, Depends(get_session)],
    lesson: Annotated[int | None, Query(description="Filtra por número da aula.")] = None,
) -> list[VocabItemWithLessonOut]:
    """Vocabulário de uma aula, ou de todas. Base do deck de revisão da S4."""
    stmt = (
        select(VocabItem, Lesson.number)
        .join(Lesson, VocabItem.lesson_id == Lesson.id)
        .order_by(Lesson.number, VocabItem.position)
    )
    if lesson is not None:
        stmt = stmt.where(Lesson.number == lesson)
    return [
        VocabItemWithLessonOut(
            **VocabItemOut.model_validate(item).model_dump(), lesson_number=numero
        )
        for item, numero in (await session.execute(stmt)).all()
    ]
