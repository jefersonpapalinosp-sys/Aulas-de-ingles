"""Consultas compartilhadas para a identidade composta curso + aula."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Course, CourseUnit, Lesson
from app.schemas.lesson import LessonSummaryOut

DEFAULT_COURSE_SLUG = "voa-level-1"


async def lesson_by_course_number(
    session: AsyncSession, course_slug: str, number: int
) -> Lesson | None:
    """Resolve uma aula sem depender da antiga unicidade global do número."""
    return (
        await session.execute(
            select(Lesson)
            .join(Course, Lesson.course_id == Course.id)
            .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
            .where(
                Course.slug == course_slug,
                Course.status == "published",
                CourseUnit.status == "published",
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
            Course.status == "published",
            CourseUnit.status == "published",
        )
        .order_by(CourseUnit.position, Lesson.position)
    )
    if unit_id is not None:
        stmt = stmt.where(Lesson.unit_id == unit_id)
    return [LessonSummaryOut.model_validate(row._mapping) for row in (await session.execute(stmt))]
