"""Painel Hoje: plano leve, recomendação explicada e competências."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, NamedTuple
from typing import cast as typing_cast
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.core.config import get_settings
from app.db.models import (
    Course,
    CourseReview,
    CourseReviewAttempt,
    CourseUnit,
    Lesson,
    LessonProgress,
    ReviewItem,
    StudyActiveInterval,
    StudyPlan,
    StudySessionProgress,
)
from app.db.session import get_session
from app.schemas.dashboard import (
    RecentSessionOut,
    RecommendationOut,
    SkillSummaryOut,
    StudyPlanIn,
    StudyPlanOut,
    TodayOut,
    Weekday,
)
from app.services.curriculum import DEFAULT_COURSE_SLUG
from app.services.dialogue_learning import conversation_recommendation
from app.services.skills import skill_summaries

router = APIRouter(prefix="/me", tags=["dashboard"])

DEFAULT_DAYS: list[Weekday] = ["mon", "wed", "fri"]


class _RecentStudy(NamedTuple):
    lesson_id: int
    current_step: str
    completed_steps: list[str]
    total_seconds: int
    updated_at: datetime
    lesson_number: int
    lesson_title: str
    course_slug: str


def _plan_out(plan: StudyPlan | None) -> StudyPlanOut:
    if plan is None:
        return StudyPlanOut(
            weekly_minutes=90,
            preferred_days=DEFAULT_DAYS,
            goal="Criar constância no inglês",
            updated_at=None,
        )
    return StudyPlanOut(
        weekly_minutes=plan.weekly_minutes,
        preferred_days=typing_cast(list[Weekday], plan.preferred_days),
        goal=plan.goal,
        timezone=plan.timezone,
        updated_at=plan.updated_at,
    )


async def _stored_plan(session: AsyncSession, user_id: int) -> StudyPlan | None:
    return (
        await session.execute(select(StudyPlan).where(StudyPlan.user_id == user_id))
    ).scalar_one_or_none()


@router.get("/study-plan", response_model=StudyPlanOut)
async def obter_plano(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StudyPlanOut:
    return _plan_out(await _stored_plan(session, usuario.id))


@router.put("/study-plan", response_model=StudyPlanOut)
async def salvar_plano(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[StudyPlanIn, Body()],
) -> StudyPlanOut:
    plan = await _stored_plan(session, usuario.id)
    if plan is None:
        plan = StudyPlan(user_id=usuario.id)
        session.add(plan)
    plan.weekly_minutes = corpo.weekly_minutes
    plan.preferred_days = list(corpo.preferred_days)
    plan.goal = corpo.goal
    plan.timezone = corpo.timezone
    plan.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(plan)
    return _plan_out(plan)


async def _recommendation(
    session: AsyncSession,
    user_id: int,
    due_reviews: int,
    course: Course,
    resume: _RecentStudy | None,
) -> RecommendationOut:
    level_label = f"Level {course.level}"
    if due_reviews:
        return RecommendationOut(
            kind="review",
            title=f"Revisar {due_reviews} {'item' if due_reviews == 1 else 'itens'}",
            reason="Esses itens já venceram no seu ciclo de revisão espaçada.",
            href=f"/revisar?{urlencode({'course': course.slug})}",
            estimated_minutes=max(5, min(15, due_reviews * 2)),
            course_slug=course.slug,
        )

    if resume is not None:
        return RecommendationOut(
            kind="continue_lesson",
            title=f"Continuar a Aula {resume.lesson_number}",
            reason=f"Você parou na etapa {resume.current_step}; retomar preserva o contexto.",
            href=(
                f"/cursos/{resume.course_slug}/aulas/{resume.lesson_number}/estudar/"
                f"{resume.current_step}"
            ),
            estimated_minutes=10,
            course_slug=resume.course_slug,
            lesson_number=resume.lesson_number,
        )

    studied_lesson_ids = (
        select(LessonProgress.lesson_id)
        .join(Lesson, LessonProgress.lesson_id == Lesson.id)
        .where(
            LessonProgress.user_id == user_id,
            Lesson.course_id == course.id,
        )
    )
    completed_current_review = (
        select(CourseReviewAttempt.id)
        .where(
            CourseReviewAttempt.user_id == user_id,
            CourseReviewAttempt.review_id == CourseReview.id,
            CourseReviewAttempt.content_version == CourseReview.content_version,
        )
        .exists()
    )
    required_lesson = Lesson.__table__.alias("required_lesson")
    studied_required = (
        select(LessonProgress.id)
        .where(
            LessonProgress.user_id == user_id,
            LessonProgress.lesson_id == required_lesson.c.id,
        )
        .correlate(required_lesson)
        .exists()
    )
    missing_required = (
        select(required_lesson.c.id)
        .where(
            required_lesson.c.course_id == Course.id,
            or_(
                required_lesson.c.unit_id == CourseUnit.id,
                required_lesson.c.number == CourseReview.review_lesson_number,
            ),
            ~studied_required,
        )
        .correlate(CourseReview, CourseUnit, Course)
        .exists()
    )
    review = (
        await session.execute(
            select(
                CourseReview.title,
                CourseReview.estimated_minutes,
                CourseUnit.slug.label("unit_slug"),
                Course.slug.label("course_slug"),
            )
            .join(CourseUnit, CourseReview.unit_id == CourseUnit.id)
            .join(Course, CourseUnit.course_id == Course.id)
            .where(
                CourseReview.status == "published",
                CourseUnit.status == "published",
                Course.status == "published",
                Course.id == course.id,
                ~completed_current_review,
                ~missing_required,
            )
            .order_by(Course.position, CourseUnit.position, CourseReview.position)
            .limit(1)
        )
    ).one_or_none()
    if review is not None:
        return RecommendationOut(
            kind="course_review",
            title=f"{review.title} · {level_label}",
            reason="Você concluiu as aulas da unidade; agora consolide o bloco.",
            href=(f"/cursos/{review.course_slug}/unidades/{review.unit_slug}/checkpoint"),
            estimated_minutes=review.estimated_minutes,
            course_slug=review.course_slug,
        )

    if get_settings().dialogue_practice_enabled:
        conversation = await conversation_recommendation(session, user_id, course)
        if conversation is not None:
            return conversation

    next_lesson = (
        await session.execute(
            select(
                Lesson.number,
                Course.slug.label("course_slug"),
            )
            .join(Course, Lesson.course_id == Course.id)
            .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
            .where(Lesson.id.not_in(studied_lesson_ids))
            .where(
                Lesson.course_id == course.id,
                CourseUnit.status == "published",
            )
            .order_by(Course.position, CourseUnit.position, Lesson.position)
            .limit(1)
        )
    ).one_or_none()
    if next_lesson is not None:
        return RecommendationOut(
            kind="start_lesson",
            title=f"Começar a Aula {next_lesson.number}",
            reason="É a próxima aula ainda não concluída na sequência do bloco.",
            href=f"/cursos/{next_lesson.course_slug}/aulas/{next_lesson.number}/estudar",
            estimated_minutes=20,
            course_slug=next_lesson.course_slug,
            lesson_number=next_lesson.number,
        )

    return RecommendationOut(
        kind="practice",
        title="Revisitar seu caderno",
        reason="Você concluiu o bloco; agora vale transformar anotações em prática livre.",
        href=f"/caderno?{urlencode({'course': course.slug})}",
        estimated_minutes=10,
        course_slug=course.slug,
    )


async def _due_reviews(session: AsyncSession, user_id: int, course_id: int, now: datetime) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(ReviewItem)
            .join(Lesson, ReviewItem.lesson_id == Lesson.id)
            .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
            .where(
                ReviewItem.user_id == user_id,
                ReviewItem.status == "active",
                ReviewItem.due_at <= now,
                Lesson.course_id == course_id,
                CourseUnit.status == "published",
            )
        )
    ).scalar_one()


async def _recent_study(
    session: AsyncSession, user_id: int, course_id: int, due_reviews: int
) -> tuple[_RecentStudy | None, _RecentStudy | None]:
    """Última sessão e o ponto de retomada, nessa ordem.

    Uma aula com os cinco passos concluídos está terminada: retomar ali
    devolveria o aluno ao fim. Sem revisão vencida, o painel prefere a sessão
    anterior ainda em aberto.
    """
    query = (
        select(
            StudySessionProgress.lesson_id,
            StudySessionProgress.current_step,
            StudySessionProgress.completed_steps,
            StudySessionProgress.total_seconds,
            StudySessionProgress.updated_at,
            Lesson.number,
            Lesson.title,
            Course.slug.label("course_slug"),
        )
        .join(Lesson, StudySessionProgress.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            StudySessionProgress.user_id == user_id,
            Lesson.course_id == course_id,
            CourseUnit.status == "published",
        )
        .order_by(StudySessionProgress.updated_at.desc())
    )
    latest_row = (await session.execute(query.limit(1))).one_or_none()
    latest = _RecentStudy(*latest_row) if latest_row is not None else None
    if due_reviews or latest is None or len(latest.completed_steps) < 5:
        return latest, latest
    resume_row = (
        await session.execute(
            query.where(func.jsonb_array_length(StudySessionProgress.completed_steps) < 5).limit(1)
        )
    ).one_or_none()
    return latest, (_RecentStudy(*resume_row) if resume_row is not None else None)


def _week_start(local_now: datetime) -> datetime:
    """Segunda-feira 00:00 no fuso do plano, convertida para UTC."""
    return (
        (local_now - timedelta(days=local_now.weekday()))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
    )


async def _week_seconds(
    session: AsyncSession, user_id: int, course_id: int, week_start: datetime, now: datetime
) -> int:
    """Segundos ativos da semana, recortando cada intervalo à janela medida."""
    total = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(
                        func.extract(
                            "epoch",
                            func.least(StudyActiveInterval.ends_at, now)
                            - func.greatest(StudyActiveInterval.starts_at, week_start),
                        )
                    ),
                    0,
                )
            )
            .join(Lesson, StudyActiveInterval.lesson_id == Lesson.id)
            .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
            .where(
                StudyActiveInterval.user_id == user_id,
                StudyActiveInterval.ends_at > week_start,
                StudyActiveInterval.starts_at < now,
                Lesson.course_id == course_id,
                CourseUnit.status == "published",
            )
        )
    ).scalar_one()
    return max(0, int(total))


async def _recent_session_out(
    session: AsyncSession, user_id: int, latest: _RecentStudy
) -> RecentSessionOut:
    """``total_minutes`` vem do tempo ativo medido; ``legacy_minutes`` é o
    acumulado antigo da sessão, mantido para comparação."""
    active_seconds = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(
                        func.extract(
                            "epoch", StudyActiveInterval.ends_at - StudyActiveInterval.starts_at
                        )
                    ),
                    0,
                )
            ).where(
                StudyActiveInterval.user_id == user_id,
                StudyActiveInterval.lesson_id == latest.lesson_id,
            )
        )
    ).scalar_one()
    return RecentSessionOut(
        course_slug=latest.course_slug,
        lesson_number=latest.lesson_number,
        lesson_title=latest.lesson_title,
        current_step=latest.current_step,
        completed_steps=len(latest.completed_steps),
        total_minutes=max(0, int(active_seconds) // 60),
        legacy_minutes=max(0, round(latest.total_seconds / 60)),
        updated_at=latest.updated_at,
    )


@router.get("/today", response_model=TodayOut)
async def painel_hoje(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    course: Annotated[str, Query(max_length=100)] = DEFAULT_COURSE_SLUG,
) -> TodayOut:
    response.headers["Cache-Control"] = "private, no-store"
    selected_course = (
        await session.execute(
            select(Course).where(
                Course.slug == course,
                Course.status == "published",
            )
        )
    ).scalar_one_or_none()
    if selected_course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Curso publicado {course!r} não existe.",
        )

    now = datetime.now(UTC)
    due_reviews = await _due_reviews(session, usuario.id, selected_course.id, now)
    latest, resume = await _recent_study(session, usuario.id, selected_course.id, due_reviews)
    plan = _plan_out(await _stored_plan(session, usuario.id))
    week_start = _week_start(now.astimezone(ZoneInfo(plan.timezone)))
    seconds = await _week_seconds(session, usuario.id, selected_course.id, week_start, now)
    return TodayOut(
        recommendation=await _recommendation(
            session,
            usuario.id,
            due_reviews,
            selected_course,
            resume,
        ),
        plan=plan,
        recorded_minutes_this_week=seconds // 60,
        recent_session=(
            await _recent_session_out(session, usuario.id, latest) if latest is not None else None
        ),
    )


@router.get("/skills", response_model=list[SkillSummaryOut])
async def minhas_competencias(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
) -> list[SkillSummaryOut]:
    response.headers["Cache-Control"] = "private, no-store"
    if unit is not None and course is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O parâmetro course é obrigatório quando unit é informado.",
        )
    return await skill_summaries(session, usuario.id, course, unit)
