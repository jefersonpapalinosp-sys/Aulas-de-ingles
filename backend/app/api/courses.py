"""Catálogo e currículo navegável dos cursos."""

from typing import Annotated, Literal, NamedTuple, cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.models import (
    Course,
    CourseReview,
    CourseReviewAttempt,
    CourseUnit,
    Lesson,
    LessonProgress,
    StudySessionProgress,
)
from app.db.session import get_session
from app.schemas.completion import (
    CertificateEligibilityOut,
    CheckpointCompletionOut,
    CompletionCourseOut,
    CourseCompletionOut,
    CourseCompletionProgressOut,
    CourseDiagnosticOut,
    IncompleteUnitOut,
    NextCourseOut,
    PendingCheckpointOut,
)
from app.schemas.lesson import (
    CourseCurriculumOut,
    CourseReviewSummaryOut,
    CourseSummaryOut,
    CourseUnitOut,
    LessonDetailOut,
)
from app.services.curriculum import lesson_by_course_number, lesson_summaries
from app.services.skills import skill_summaries

router = APIRouter(prefix="/courses", tags=["courses"])


class _CompletionUnit(NamedTuple):
    id: int
    slug: str
    title: str
    position: int
    status: str
    lesson_start: int
    lesson_end: int
    total_lessons: int


class _CompletionReview(NamedTuple):
    id: int
    title: str
    content_version: int
    source_url: str | None
    unit_slug: str


def _review_out(unit: CourseUnit) -> CourseReviewSummaryOut | None:
    review = unit.review
    if unit.status != "published" or review is None or review.status != "published":
        return None
    return CourseReviewSummaryOut.model_validate(
        {
            "id": review.id,
            "slug": review.slug,
            "title": review.title,
            "position": review.position,
            "status": review.status,
            "source_kind": review.source_kind,
            "estimated_minutes": review.estimated_minutes,
            "review_lesson_number": review.review_lesson_number,
            "question_count": len(review.questions),
        }
    )


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


async def _course_with_count(session: AsyncSession, course_slug: str) -> tuple[Course, int] | None:
    published = (
        select(func.count(Lesson.id))
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            Lesson.course_id == Course.id,
            CourseUnit.status == "published",
        )
        .correlate(Course)
        .scalar_subquery()
    )
    row = (
        await session.execute(select(Course, published).where(Course.slug == course_slug))
    ).one_or_none()
    if row is None:
        return None
    return row[0], int(row[1])


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


def _completion_status(
    published_lessons: int, completed_lessons: int, has_activity: bool
) -> Literal["not_started", "in_progress", "completed"]:
    if published_lessons > 0 and completed_lessons == published_lessons:
        return "completed"
    if has_activity:
        return "in_progress"
    return "not_started"


@router.get("/{course_slug}/completion", response_model=CourseCompletionOut)
async def get_course_completion(
    course_slug: str,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> CourseCompletionOut:
    """Resume o recorte publicado sem alterar progresso ou emitir arquivo.

    ``viewed_lessons`` é a união das aulas com sessão iniciada e das aulas
    concluídas. ``completed_lessons`` considera exclusivamente
    :class:`LessonProgress`. Um checkpoint só conta quando existe tentativa na
    ``content_version`` publicada atualmente.
    """

    _private(response)
    course = (
        await session.execute(
            select(Course).where(
                Course.slug == course_slug,
                Course.status == "published",
            )
        )
    ).scalar_one_or_none()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Curso publicado {course_slug!r} não existe.",
            headers={"Cache-Control": "private, no-store"},
        )

    unit_rows = (
        await session.execute(
            select(
                CourseUnit.id,
                CourseUnit.slug,
                CourseUnit.title,
                CourseUnit.position,
                CourseUnit.status,
                CourseUnit.lesson_start,
                CourseUnit.lesson_end,
                CourseUnit.total_lessons,
            )
            .where(CourseUnit.course_id == course.id)
            .order_by(CourseUnit.position)
        )
    ).all()
    all_units = [_CompletionUnit(*row) for row in unit_rows]
    published_units = [unit for unit in all_units if unit.status == "published"]
    unit_ids = [unit.id for unit in published_units]
    lesson_rows = (
        await session.execute(
            select(Lesson.id, Lesson.unit_id)
            .where(
                Lesson.course_id == course.id,
                Lesson.unit_id.in_(unit_ids),
            )
            .order_by(Lesson.position)
        )
    ).all()
    lesson_ids = [lesson_id for lesson_id, _unit_id in lesson_rows]

    completed_ids: set[int] = set()
    started_ids: set[int] = set()
    if lesson_ids:
        completed_ids = set(
            (
                await session.execute(
                    select(LessonProgress.lesson_id).where(
                        LessonProgress.user_id == usuario.id,
                        LessonProgress.lesson_id.in_(lesson_ids),
                    )
                )
            ).scalars()
        )
        started_ids = set(
            (
                await session.execute(
                    select(StudySessionProgress.lesson_id).where(
                        StudySessionProgress.user_id == usuario.id,
                        StudySessionProgress.lesson_id.in_(lesson_ids),
                    )
                )
            ).scalars()
        )
    viewed_ids = completed_ids | started_ids

    lesson_ids_by_unit: dict[int, set[int]] = {unit.id: set() for unit in published_units}
    for lesson_id, unit_id in lesson_rows:
        lesson_ids_by_unit[unit_id].add(lesson_id)

    incomplete_units: list[IncompleteUnitOut] = []
    for unit in published_units:
        published_ids = lesson_ids_by_unit[unit.id]
        if not published_ids or published_ids <= completed_ids:
            continue
        incomplete_units.append(
            IncompleteUnitOut(
                slug=unit.slug,
                title=unit.title,
                published_lessons=len(published_ids),
                viewed_lessons=len(published_ids & viewed_ids),
                completed_lessons=len(published_ids & completed_ids),
                href=f"/cursos/{course.slug}/unidades/{unit.slug}",
            )
        )

    raw_review_rows = (
        await session.execute(
            select(
                CourseReview.id,
                CourseReview.title,
                CourseReview.content_version,
                CourseReview.source_url,
                CourseUnit.slug,
            )
            .join(CourseUnit, CourseReview.unit_id == CourseUnit.id)
            .where(
                CourseUnit.course_id == course.id,
                CourseUnit.status == "published",
                CourseReview.status == "published",
            )
            .order_by(CourseUnit.position, CourseReview.position)
        )
    ).all()
    review_rows = [_CompletionReview(*row) for row in raw_review_rows]
    review_ids = [review.id for review in review_rows]
    current_review_ids: set[int] = set()
    if review_ids:
        current_review_ids = set(
            (
                await session.execute(
                    select(CourseReviewAttempt.review_id)
                    .join(
                        CourseReview,
                        CourseReviewAttempt.review_id == CourseReview.id,
                    )
                    .where(
                        CourseReviewAttempt.user_id == usuario.id,
                        CourseReviewAttempt.review_id.in_(review_ids),
                        CourseReviewAttempt.content_version == CourseReview.content_version,
                    )
                    .distinct()
                )
            ).scalars()
        )
    pending_checkpoints = [
        PendingCheckpointOut(
            unit_slug=review.unit_slug,
            title=review.title,
            content_version=review.content_version,
            href=f"/cursos/{course.slug}/unidades/{review.unit_slug}/checkpoint",
        )
        for review in review_rows
        if review.id not in current_review_ids
    ]

    published_count = len(lesson_rows)
    viewed_count = len(viewed_ids)
    completed_count = len(completed_ids)
    skills = await skill_summaries(session, usuario.id, course.slug)
    has_activity = bool(
        viewed_count or current_review_ids or any(skill.samples > 0 for skill in skills)
    )
    required_lessons = sum(unit.total_lessons for unit in all_units if unit.status != "archived")
    declared_units = [unit for unit in all_units if unit.status != "archived"]
    if declared_units:
        scope_start = min(unit.lesson_start for unit in declared_units)
        scope_end = max(unit.lesson_end for unit in declared_units)
        scope_label = (
            f"Aula {scope_start}"
            if scope_start == scope_end
            else f"Aulas {scope_start}–{scope_end}"
        )
    else:
        scope_label = course.title
    required_checkpoints = len(review_rows)
    all_content_published = bool(declared_units) and all(
        unit.status == "published"
        and len(lesson_ids_by_unit.get(unit.id, set())) == unit.total_lessons
        for unit in declared_units
    )
    lessons_complete = all_content_published and completed_count == required_lessons
    checkpoints_complete = len(current_review_ids) == required_checkpoints
    eligible = lessons_complete and checkpoints_complete

    if eligible:
        certificate_reason = (
            f"As {required_lessons} aulas do recorte e os {required_checkpoints} "
            "checkpoints atuais foram concluídos."
        )
        certificate_label = "Consultar revisão e certificado na VOA"
        certificate_href = (
            review_rows[-1].source_url
            if review_rows and review_rows[-1].source_url
            else course.source_url
        )
    elif not all_content_published:
        certificate_reason = (
            "O recorte ainda possui unidades em preparação ou com quantidade de aulas "
            f"diferente do planejado: {published_count} aulas disponíveis para "
            f"{required_lessons} previstas."
        )
        certificate_label = "Ver curso"
        certificate_href = f"/cursos/{course.slug}"
    elif completed_count < required_lessons:
        remaining = required_lessons - completed_count
        certificate_reason = (
            f"Conclua {remaining} {'aula' if remaining == 1 else 'aulas'} "
            "do recorte para liberar o certificado."
        )
        certificate_label = "Continuar estudando"
        certificate_href = (
            incomplete_units[0].href if incomplete_units else f"/cursos/{course.slug}"
        )
    else:
        remaining = required_checkpoints - len(current_review_ids)
        certificate_reason = (
            f"Conclua {remaining} "
            f"{'checkpoint atual' if remaining == 1 else 'checkpoints atuais'} "
            "para liberar o certificado."
        )
        certificate_label = "Fazer checkpoint"
        certificate_href = (
            pending_checkpoints[0].href if pending_checkpoints else f"/cursos/{course.slug}"
        )

    next_course = (
        await session.execute(
            select(Course)
            .where(
                Course.position > course.position,
                Course.status != "archived",
            )
            .order_by(Course.position)
            .limit(1)
        )
    ).scalar_one_or_none()
    next_course_out = None
    if next_course is not None:
        next_course_out = NextCourseOut(
            slug=next_course.slug,
            title=next_course.title,
            level=next_course.level,
            proficiency_label=next_course.proficiency_label,
            status=cast(Literal["planned", "published", "archived"], next_course.status),
            href=f"/cursos/{next_course.slug}",
            preview=(
                f"{next_course.title} · {next_course.proficiency_label}, "
                f"por {next_course.provider}."
            ),
            diagnostic=CourseDiagnosticOut(
                title=f"Preparação para {next_course.title}",
                description=(
                    "Faça uma autoavaliação curta antes de decidir se quer "
                    f"começar {next_course.title}."
                ),
                href=f"/cursos/{course.slug}/conclusao#diagnostico",
            ),
        )

    return CourseCompletionOut(
        course=CompletionCourseOut(
            slug=course.slug,
            title=course.title,
            level=course.level,
            proficiency_label=course.proficiency_label,
        ),
        progress=CourseCompletionProgressOut(
            published_lessons=published_count,
            viewed_lessons=viewed_count,
            completed_lessons=completed_count,
            completion_percent=(
                round((completed_count / published_count) * 100) if published_count else 0
            ),
            status=_completion_status(published_count, completed_count, has_activity),
        ),
        incomplete_units=incomplete_units,
        checkpoints=CheckpointCompletionOut(
            published=required_checkpoints,
            current_completed=len(current_review_ids),
            pending=pending_checkpoints,
        ),
        skills=skills,
        certificate=CertificateEligibilityOut(
            eligible=eligible,
            status="eligible" if eligible else "ineligible",
            reason=certificate_reason,
            required_lessons=required_lessons,
            required_checkpoints=required_checkpoints,
            scope_label=scope_label,
            cta_label=certificate_label,
            cta_href=certificate_href,
            automatic_download=False,
        ),
        next_course=next_course_out,
    )


@router.get("", response_model=list[CourseSummaryOut])
async def list_courses(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CourseSummaryOut]:
    """Lista cursos publicados e planejados sem materializar aulas completas."""
    published = (
        select(func.count(Lesson.id))
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            Lesson.course_id == Course.id,
            CourseUnit.status == "published",
        )
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
        .where(
            Lesson.unit_id == CourseUnit.id,
            CourseUnit.status == "published",
        )
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
                "review": _review_out(unit),
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
