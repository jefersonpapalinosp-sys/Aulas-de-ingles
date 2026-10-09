"""Leitura do conteúdo das aulas. Tudo público nesta sprint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Course, CourseUnit, Exercise, Lesson, VocabItem
from app.db.session import get_session
from app.schemas.lesson import (
    ExerciseOut,
    ExerciseWithLessonOut,
    LessonDetailOut,
    LessonSummaryOut,
    VocabItemOut,
    VocabItemWithLessonOut,
    exercise_public_payload,
)
from app.services.curriculum import (
    DEFAULT_COURSE_SLUG,
    lesson_by_course_number,
    lesson_summaries,
)

router = APIRouter(tags=["lessons"])


@router.get("/lessons", response_model=list[LessonSummaryOut])
async def listar_aulas(
    session: Annotated[AsyncSession, Depends(get_session)],
    course: Annotated[
        str, Query(description="Slug do curso; o padrão mantém o endpoint legado no Level 1.")
    ] = DEFAULT_COURSE_SLUG,
) -> list[LessonSummaryOut]:
    """Todas as aulas, em ordem, com o mínimo para montar a navegação."""
    return await lesson_summaries(session, course)


@router.get("/lessons/{number}", response_model=LessonDetailOut)
async def obter_aula(
    number: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Lesson:
    """Uma aula inteira: gramática, frases, vocabulário, pronúncia e exercícios."""
    lesson = await lesson_by_course_number(session, DEFAULT_COURSE_SLUG, number)
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Aula {number} não existe."
        )
    return lesson


@router.get("/vocab", response_model=list[VocabItemWithLessonOut])
async def listar_vocabulario(
    session: Annotated[AsyncSession, Depends(get_session)],
    lesson: Annotated[int | None, Query(description="Filtra por número da aula.")] = None,
    course: Annotated[
        str, Query(description="Slug do curso; o padrão mantém a consulta no Level 1.")
    ] = DEFAULT_COURSE_SLUG,
) -> list[VocabItemWithLessonOut]:
    """Vocabulário de uma aula, ou de todas. Base do deck de revisão da S4."""
    stmt = (
        select(VocabItem, Lesson.number)
        .join(Lesson, VocabItem.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            Course.slug == course,
            Course.status == "published",
            CourseUnit.status == "published",
        )
        .order_by(CourseUnit.position, Lesson.position, VocabItem.position)
    )
    if lesson is not None:
        stmt = stmt.where(Lesson.number == lesson)
    return [
        VocabItemWithLessonOut(
            **VocabItemOut.model_validate(item).model_dump(), lesson_number=numero
        )
        for item, numero in (await session.execute(stmt)).all()
    ]


@router.get("/exercises", response_model=list[ExerciseWithLessonOut])
async def listar_exercicios(
    session: Annotated[AsyncSession, Depends(get_session)],
    lesson: Annotated[int | None, Query(description="Filtra por número da aula.")] = None,
    course: Annotated[
        str, Query(description="Slug do curso; o padrão mantém a consulta no Level 1.")
    ] = DEFAULT_COURSE_SLUG,
    unit: Annotated[
        str | None, Query(description="Limita a avaliação a uma unidade do curso.")
    ] = None,
) -> list[ExerciseWithLessonOut]:
    """Exercícios de uma aula, unidade ou curso.

    É o que a prova do bloco consome: sem isso a tela teria que baixar as dez
    aulas inteiras para montar uma lista de exercícios.
    """
    stmt = (
        select(Exercise, Course.slug, CourseUnit.slug, Lesson.number)
        .join(Lesson, Exercise.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            Course.slug == course,
            Course.status == "published",
            CourseUnit.status == "published",
        )
        .order_by(CourseUnit.position, Lesson.position, Exercise.position)
    )
    if lesson is not None:
        stmt = stmt.where(Lesson.number == lesson)
    if unit is not None:
        stmt = stmt.where(CourseUnit.slug == unit)
    return [
        ExerciseWithLessonOut(
            **ExerciseOut.model_validate(exercise_public_payload(item)).model_dump(),
            course_slug=course_slug,
            unit_slug=unit_slug,
            lesson_number=numero,
        )
        for item, course_slug, unit_slug, numero in (await session.execute(stmt)).all()
    ]
