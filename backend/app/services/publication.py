"""Publication boundary for current study, not ownership of historical data.

Archiving a course/unit hides its current curriculum and prevents new curricular
activity. Owned drafts, audio, snapshots and copied review cards remain personal
data: their read/export/delete paths must not call this guard.
"""

from fastapi import HTTPException
from sqlalchemy import Select, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Course, CourseUnit, Lesson

# Shared by all admission paths and the exclusive archive/seed operation.
# Transaction-scoped, non-blocking: no lock survives commit/rollback, and no
# cycle with pre-existing user/practice row locks can wait indefinitely.
PUBLICATION_LOCK = (74040, 1)


async def lock_publication(session: AsyncSession) -> None:
    acquired = await session.scalar(
        text("SELECT pg_try_advisory_xact_lock_shared(:namespace, :key)"),
        {"namespace": PUBLICATION_LOCK[0], "key": PUBLICATION_LOCK[1]},
    )
    if not acquired:
        raise HTTPException(503, "Catálogo em manutenção; tente novamente em instantes.")


def published_scope() -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """For queries that already join Course and CourseUnit explicitly."""
    return Course.status == "published", CourseUnit.status == "published"


def published_lesson_ids() -> Select[int]:
    """Uncorrelated subquery, safe even if an outer query also joins Lesson."""
    return (
        select(Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(*published_scope())
        .correlate(None)
    )


async def require_published_lesson(session: AsyncSession, lesson_id: int) -> None:
    await lock_publication(session)
    exists = await session.scalar(published_lesson_ids().where(Lesson.id == lesson_id))
    if exists is None:
        raise HTTPException(404, detail="Conteúdo não está disponível para novas atividades.")
