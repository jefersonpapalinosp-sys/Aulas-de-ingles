"""Conclusão de curso: recorte publicado, pendências e elegibilidade.

Só lê. Nada aqui altera progresso, emite arquivo ou promete certificado
automático — a elegibilidade é uma leitura do estado, e o destino do aluno é
sempre um endereço da VOA ou do próprio app.

Três contagens convivem e não devem ser confundidas:

``published_lessons``
    aulas publicadas no recorte.
``viewed_lessons``
    união das aulas com sessão iniciada e das concluídas.
``completed_lessons``
    exclusivamente :class:`LessonProgress`.

Um checkpoint só conta quando existe tentativa na ``content_version``
publicada atualmente; versão nova devolve o checkpoint à lista de pendências.
"""

from typing import Literal, NamedTuple, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Course,
    CourseReview,
    CourseReviewAttempt,
    CourseUnit,
    Lesson,
    LessonProgress,
    StudySessionProgress,
)
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
from app.schemas.dashboard import SkillSummaryOut
from app.services.skills import skill_summaries


class CompletionUnit(NamedTuple):
    id: int
    slug: str
    title: str
    position: int
    status: str
    lesson_start: int
    lesson_end: int
    total_lessons: int


class CompletionReview(NamedTuple):
    id: int
    title: str
    content_version: int
    source_url: str | None
    unit_slug: str


async def _units(session: AsyncSession, course_id: int) -> list[CompletionUnit]:
    rows = (
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
            .where(CourseUnit.course_id == course_id)
            .order_by(CourseUnit.position)
        )
    ).all()
    return [CompletionUnit(*row) for row in rows]


async def _lesson_rows(
    session: AsyncSession, course_id: int, unit_ids: list[int]
) -> list[tuple[int, int]]:
    rows = (
        await session.execute(
            select(Lesson.id, Lesson.unit_id)
            .where(Lesson.course_id == course_id, Lesson.unit_id.in_(unit_ids))
            .order_by(Lesson.position)
        )
    ).all()
    return [(int(lesson_id), int(unit_id)) for lesson_id, unit_id in rows]


async def _progress_ids(
    session: AsyncSession, user_id: int, lesson_ids: list[int]
) -> tuple[set[int], set[int]]:
    """Aulas concluídas e aulas com sessão iniciada, nessa ordem."""
    if not lesson_ids:
        return set(), set()
    completed = set(
        (
            await session.execute(
                select(LessonProgress.lesson_id).where(
                    LessonProgress.user_id == user_id,
                    LessonProgress.lesson_id.in_(lesson_ids),
                )
            )
        ).scalars()
    )
    started = set(
        (
            await session.execute(
                select(StudySessionProgress.lesson_id).where(
                    StudySessionProgress.user_id == user_id,
                    StudySessionProgress.lesson_id.in_(lesson_ids),
                )
            )
        ).scalars()
    )
    return completed, started


def _incomplete_units(
    course_slug: str,
    published_units: list[CompletionUnit],
    lesson_ids_by_unit: dict[int, set[int]],
    completed_ids: set[int],
    viewed_ids: set[int],
) -> list[IncompleteUnitOut]:
    incomplete: list[IncompleteUnitOut] = []
    for unit in published_units:
        published_ids = lesson_ids_by_unit[unit.id]
        if not published_ids or published_ids <= completed_ids:
            continue
        incomplete.append(
            IncompleteUnitOut(
                slug=unit.slug,
                title=unit.title,
                published_lessons=len(published_ids),
                viewed_lessons=len(published_ids & viewed_ids),
                completed_lessons=len(published_ids & completed_ids),
                href=f"/cursos/{course_slug}/unidades/{unit.slug}",
            )
        )
    return incomplete


async def _reviews(session: AsyncSession, course_id: int) -> list[CompletionReview]:
    rows = (
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
                CourseUnit.course_id == course_id,
                CourseUnit.status == "published",
                CourseReview.status == "published",
            )
            .order_by(CourseUnit.position, CourseReview.position)
        )
    ).all()
    return [CompletionReview(*row) for row in rows]


async def _current_review_ids(
    session: AsyncSession, user_id: int, review_ids: list[int]
) -> set[int]:
    """Checkpoints com tentativa na ``content_version`` publicada hoje."""
    if not review_ids:
        return set()
    return set(
        (
            await session.execute(
                select(CourseReviewAttempt.review_id)
                .join(CourseReview, CourseReviewAttempt.review_id == CourseReview.id)
                .where(
                    CourseReviewAttempt.user_id == user_id,
                    CourseReviewAttempt.review_id.in_(review_ids),
                    CourseReviewAttempt.content_version == CourseReview.content_version,
                )
                .distinct()
            )
        ).scalars()
    )


def _pending_checkpoints(
    course_slug: str, reviews: list[CompletionReview], current_review_ids: set[int]
) -> list[PendingCheckpointOut]:
    return [
        PendingCheckpointOut(
            unit_slug=review.unit_slug,
            title=review.title,
            content_version=review.content_version,
            href=f"/cursos/{course_slug}/unidades/{review.unit_slug}/checkpoint",
        )
        for review in reviews
        if review.id not in current_review_ids
    ]


def _scope_label(course: Course, declared_units: list[CompletionUnit]) -> str:
    if not declared_units:
        return course.title
    start = min(unit.lesson_start for unit in declared_units)
    end = max(unit.lesson_end for unit in declared_units)
    return f"Aula {start}" if start == end else f"Aulas {start}–{end}"


def _completion_status(
    published_lessons: int, completed_lessons: int, has_activity: bool
) -> Literal["not_started", "in_progress", "completed"]:
    if published_lessons > 0 and completed_lessons == published_lessons:
        return "completed"
    if has_activity:
        return "in_progress"
    return "not_started"


class _Certificate(NamedTuple):
    reason: str
    cta_label: str
    cta_href: str


def _certificate(
    *,
    course: Course,
    eligible: bool,
    all_content_published: bool,
    published_count: int,
    completed_count: int,
    required_lessons: int,
    required_checkpoints: int,
    completed_checkpoints: int,
    reviews: list[CompletionReview],
    incomplete_units: list[IncompleteUnitOut],
    pending_checkpoints: list[PendingCheckpointOut],
) -> _Certificate:
    """Motivo e destino do aluno. A ordem das causas é a da experiência: falta
    de conteúdo publicado vem antes de aulas pendentes, que vêm antes de
    checkpoints."""
    if eligible:
        href = reviews[-1].source_url if reviews and reviews[-1].source_url else course.source_url
        return _Certificate(
            reason=(
                f"As {required_lessons} aulas do recorte e os {required_checkpoints} "
                "checkpoints atuais foram concluídos."
            ),
            cta_label="Consultar revisão e certificado na VOA",
            cta_href=href,
        )
    if not all_content_published:
        return _Certificate(
            reason=(
                "O recorte ainda possui unidades em preparação ou com quantidade de aulas "
                f"diferente do planejado: {published_count} aulas disponíveis para "
                f"{required_lessons} previstas."
            ),
            cta_label="Ver curso",
            cta_href=f"/cursos/{course.slug}",
        )
    if completed_count < required_lessons:
        remaining = required_lessons - completed_count
        return _Certificate(
            reason=(
                f"Conclua {remaining} {'aula' if remaining == 1 else 'aulas'} "
                "do recorte para liberar o certificado."
            ),
            cta_label="Continuar estudando",
            cta_href=(incomplete_units[0].href if incomplete_units else f"/cursos/{course.slug}"),
        )
    remaining = required_checkpoints - completed_checkpoints
    return _Certificate(
        reason=(
            f"Conclua {remaining} "
            f"{'checkpoint atual' if remaining == 1 else 'checkpoints atuais'} "
            "para liberar o certificado."
        ),
        cta_label="Fazer checkpoint",
        cta_href=(pending_checkpoints[0].href if pending_checkpoints else f"/cursos/{course.slug}"),
    )


async def _next_course(session: AsyncSession, course: Course) -> NextCourseOut | None:
    following = (
        await session.execute(
            select(Course)
            .where(Course.position > course.position, Course.status != "archived")
            .order_by(Course.position)
            .limit(1)
        )
    ).scalar_one_or_none()
    if following is None:
        return None
    return NextCourseOut(
        slug=following.slug,
        title=following.title,
        level=following.level,
        proficiency_label=following.proficiency_label,
        status=cast(Literal["planned", "published", "archived"], following.status),
        href=f"/cursos/{following.slug}",
        preview=(f"{following.title} · {following.proficiency_label}, por {following.provider}."),
        diagnostic=CourseDiagnosticOut(
            title=f"Preparação para {following.title}",
            description=(
                f"Faça uma autoavaliação curta antes de decidir se quer começar {following.title}."
            ),
            href=f"/cursos/{course.slug}/conclusao#diagnostico",
        ),
    )


async def course_completion(
    session: AsyncSession, course: Course, user_id: int
) -> CourseCompletionOut:
    """Resume o recorte publicado de ``course`` para ``user_id``."""
    all_units = await _units(session, course.id)
    published_units = [unit for unit in all_units if unit.status == "published"]
    lesson_rows = await _lesson_rows(session, course.id, [unit.id for unit in published_units])
    lesson_ids = [lesson_id for lesson_id, _unit_id in lesson_rows]
    completed_ids, started_ids = await _progress_ids(session, user_id, lesson_ids)
    viewed_ids = completed_ids | started_ids

    lesson_ids_by_unit: dict[int, set[int]] = {unit.id: set() for unit in published_units}
    for lesson_id, unit_id in lesson_rows:
        lesson_ids_by_unit[unit_id].add(lesson_id)
    incomplete_units = _incomplete_units(
        course.slug, published_units, lesson_ids_by_unit, completed_ids, viewed_ids
    )

    reviews = await _reviews(session, course.id)
    current_review_ids = await _current_review_ids(
        session, user_id, [review.id for review in reviews]
    )
    pending_checkpoints = _pending_checkpoints(course.slug, reviews, current_review_ids)

    published_count = len(lesson_rows)
    completed_count = len(completed_ids)
    skills: list[SkillSummaryOut] = await skill_summaries(session, user_id, course.slug)
    has_activity = bool(
        viewed_ids or current_review_ids or any(skill.samples > 0 for skill in skills)
    )

    declared_units = [unit for unit in all_units if unit.status != "archived"]
    required_lessons = sum(unit.total_lessons for unit in declared_units)
    required_checkpoints = len(reviews)
    all_content_published = bool(declared_units) and all(
        unit.status == "published"
        and len(lesson_ids_by_unit.get(unit.id, set())) == unit.total_lessons
        for unit in declared_units
    )
    eligible = (
        all_content_published
        and completed_count == required_lessons
        and len(current_review_ids) == required_checkpoints
    )
    certificate = _certificate(
        course=course,
        eligible=eligible,
        all_content_published=all_content_published,
        published_count=published_count,
        completed_count=completed_count,
        required_lessons=required_lessons,
        required_checkpoints=required_checkpoints,
        completed_checkpoints=len(current_review_ids),
        reviews=reviews,
        incomplete_units=incomplete_units,
        pending_checkpoints=pending_checkpoints,
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
            viewed_lessons=len(viewed_ids),
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
            reason=certificate.reason,
            required_lessons=required_lessons,
            required_checkpoints=required_checkpoints,
            scope_label=_scope_label(course, declared_units),
            cta_label=certificate.cta_label,
            cta_href=certificate.cta_href,
            automatic_download=False,
        ),
        next_course=await _next_course(session, course),
    )
