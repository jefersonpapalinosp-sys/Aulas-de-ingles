"""Catálogo e currículo navegável dos cursos."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Course, CourseUnit, Lesson
from app.db.session import get_session
from app.schemas.lesson import (
    CourseCurriculumOut,
    CourseSummaryOut,
    CourseUnitOut,
    LessonDetailOut,
)
from app.services.curriculum import lesson_by_course_number, lesson_summaries

router = APIRouter(prefix="/courses", tags=["courses"])


def _course_out(course: Course, published_lessons: int) -> CourseSummaryOut:
    return CourseSummaryOut.model_validate(
        {
            "id": course.id,
            "slug": course.slug,
            "title": course.title,
            "level": course.level,
            "proficiency_label": course.proficiency_label,
            "provider": course.provider,
            "source_url": course.source_url,
            "position": course.position,
            "status": course.status,
            "total_lessons": course.total_lessons,
            "published_lessons": published_lessons,
        }
    )


async def _course_with_count(
    session: AsyncSession, course_slug: str
) -> tuple[Course, int] | None:
    published = (
        select(func.count(Lesson.id))
        .where(Lesson.course_id == Course.id)
        .correlate(Course)
        .scalar_subquery()
    )
    row = (
        await session.execute(
            select(Course, published).where(Course.slug == course_slug)
        )
    ).one_or_none()
    if row is None:
        return None
    return row[0], int(row[1])


@router.get("", response_model=list[CourseSummaryOut])
async def list_courses(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CourseSummaryOut]:
    """Lista cursos publicados e planejados sem materializar aulas completas."""
    published = (
        select(func.count(Lesson.id))
        .where(Lesson.course_id == Course.id)
        .correlate(Course)
        .scalar_subquery()
    )
    rows = (await session.execute(select(Course, published).order_by(Course.position))).all()
    return [_course_out(course, int(count)) for course, count in rows]


@router.get("/{course_slug}/curriculum", response_model=CourseCurriculumOut)
async def get_curriculum(
    course_slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CourseCurriculumOut:
    """Unidades e resumos de aula ordenados para montar catálogo e rail."""
    course_row = await _course_with_count(session, course_slug)
    if course_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Curso {course_slug!r} não existe.",
        )
    course, published_lessons = course_row
    published = (
        select(func.count(Lesson.id))
        .where(Lesson.unit_id == CourseUnit.id)
        .correlate(CourseUnit)
        .scalar_subquery()
    )
    unit_rows = (
        await session.execute(
            select(CourseUnit, published)
            .where(CourseUnit.course_id == course.id)
            .order_by(CourseUnit.position)
        )
    ).all()
    all_lessons = await lesson_summaries(session, course_slug)
    lessons_by_unit: dict[str, list[object]] = {}
    for lesson in all_lessons:
        lessons_by_unit.setdefault(lesson.unit_slug, []).append(lesson)
    units = [
        CourseUnitOut.model_validate(
            {
                "id": unit.id,
                "slug": unit.slug,
                "title": unit.title,
                "position": unit.position,
                "status": unit.status,
                "lesson_start": unit.lesson_start,
                "lesson_end": unit.lesson_end,
                "total_lessons": unit.total_lessons,
                "published_lessons": int(count),
                "lessons": lessons_by_unit.get(unit.slug, []),
            }
        )
        for unit, count in unit_rows
    ]
    return CourseCurriculumOut(course=_course_out(course, published_lessons), units=units)


@router.get("/{course_slug}/lessons/{number}", response_model=LessonDetailOut)
async def get_course_lesson(
    course_slug: str,
    number: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Lesson:
    lesson = await lesson_by_course_number(session, course_slug, number)
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aula {number} não existe no curso {course_slug!r}.",
        )
    return lesson

