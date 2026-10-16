"""Consultas compartilhadas para a identidade composta curso + aula."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defaultload, defer, raiseload

from app.db.models import Course, CourseUnit, Exercise, Lesson
from app.schemas.lesson import LessonSummaryOut
from app.services.publication import lock_publication, published_scope

DEFAULT_COURSE_SLUG = "voa-level-1"


async def lesson_by_course_number(
    session: AsyncSession, course_slug: str, number: int
) -> Lesson | None:
    """Resolve uma aula sem depender da antiga unicidade global do número."""
    await lock_publication(session)
    return (
        await session.execute(
            select(Lesson)
            .options(
                # A unidade entra no payload somente pelo slug. O checkpoint e
                # suas perguntas pertencem ao currículo, não ao detalhe da aula.
                defaultload(Lesson.unit).raiseload(CourseUnit.review),
                # Gabaritos e explicações são liberados somente pelos fluxos
                # autenticados de correção/feedback.
                defaultload(Lesson.exercises).options(
                    raiseload(Exercise.answers),
                    defer(Exercise.hint),
                    defer(Exercise.explanation),
                ),
            )
            .join(Course, Lesson.course_id == Course.id)
            .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
            .where(
                Course.slug == course_slug,
                *published_scope(),
                Lesson.number == number,
            )
        )
    ).scalar_one_or_none()


async def lesson_summaries(
    session: AsyncSession, course_slug: str, unit_id: int | None = None
) -> list[LessonSummaryOut]:
    """Retorna somente colunas de navegação, sem hidratar o conteúdo da aula."""
    stmt = (
        select(
            Lesson.id,
            Course.slug.label("course_slug"),
            CourseUnit.slug.label("unit_slug"),
            Lesson.slug,
            Lesson.position,
            Lesson.number,
            Lesson.title,
            Lesson.title_pt,
            Lesson.grammar_tag,
            Lesson.focus_points,
            Lesson.story_note,
        )
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            Course.slug == course_slug,
            *published_scope(),
        )
        .order_by(CourseUnit.position, Lesson.position)
    )
    if unit_id is not None:
        stmt = stmt.where(Lesson.unit_id == unit_id)
    return [LessonSummaryOut.model_validate(row._mapping) for row in (await session.execute(stmt))]
