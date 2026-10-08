"""Painel Hoje: plano leve, recomendação explicada e competências."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from typing import cast as typing_cast

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import Integer, Select, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.models import (
    Course,
    CourseReview,
    CourseReviewAttempt,
    CourseUnit,
    Exercise,
    ExerciseAttempt,
    Lesson,
    LessonMedia,
    LessonProgress,
    ReviewItem,
    SkillEvidence,
    SpeakingAttempt,
    StudyPlan,
    StudySessionProgress,
    TranscriptCue,
    WritingFeedbackRecord,
    WritingPrompt,
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

router = APIRouter(prefix="/me", tags=["dashboard"])

DEFAULT_DAYS: list[Weekday] = ["mon", "wed", "fri"]
SKILL_LABELS = {
    "grammar": "Gramática",
    "listening": "Compreensão oral",
    "writing": "Escrita",
    "speaking": "Fala",
}


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
    plan.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(plan)
    return _plan_out(plan)


async def _recommendation(
    session: AsyncSession, user_id: int, due_reviews: int
) -> RecommendationOut:
    if due_reviews:
        return RecommendationOut(
            kind="review",
            title=f"Revisar {due_reviews} {'item' if due_reviews == 1 else 'itens'}",
            reason="Esses itens já venceram no seu ciclo de revisão espaçada.",
            href="/revisar",
            estimated_minutes=max(5, min(15, due_reviews * 2)),
        )

    resume = (
        await session.execute(
            select(StudySessionProgress, Lesson)
            .join(Lesson, StudySessionProgress.lesson_id == Lesson.id)
            .where(
                StudySessionProgress.user_id == user_id,
                func.jsonb_array_length(StudySessionProgress.completed_steps) < 5,
            )
            .order_by(StudySessionProgress.updated_at.desc())
            .limit(1)
        )
    ).one_or_none()
    if resume is not None:
        study, lesson = resume
        return RecommendationOut(
            kind="continue_lesson",
            title=f"Continuar a Aula {lesson.number}",
            reason=f"Você parou na etapa {study.current_step}; retomar preserva o contexto.",
            href=(
                f"/cursos/{lesson.course_slug}/aulas/{lesson.number}/estudar/"
                f"{study.current_step}"
            ),
            estimated_minutes=10,
            course_slug=lesson.course_slug,
            lesson_number=lesson.number,
        )

    studied_lesson_ids = select(LessonProgress.lesson_id).where(LessonProgress.user_id == user_id)
    completed_current_review = (
        select(CourseReviewAttempt.id)
        .where(
            CourseReviewAttempt.user_id == user_id,
            CourseReviewAttempt.review_id == CourseReview.id,
            CourseReviewAttempt.content_version == CourseReview.content_version,
        )
        .exists()
    )
    reviews = (
        await session.execute(
            select(CourseReview, CourseUnit, Course)
            .join(CourseUnit, CourseReview.unit_id == CourseUnit.id)
            .join(Course, CourseUnit.course_id == Course.id)
            .where(
                CourseReview.status == "published",
                CourseUnit.status == "published",
                Course.status == "published",
                ~completed_current_review,
            )
            .order_by(Course.position, CourseUnit.position, CourseReview.position)
        )
    ).all()
    for course_review, unit, course in reviews:
        required_ids = select(Lesson.id).where(
            (Lesson.unit_id == unit.id)
            | (
                (Lesson.course_id == course.id)
                & (Lesson.number == course_review.review_lesson_number)
            )
        )
        missing_required = (
            await session.execute(
                select(func.count())
                .select_from(Lesson)
                .where(Lesson.id.in_(required_ids), Lesson.id.not_in(studied_lesson_ids))
            )
        ).scalar_one()
        if missing_required == 0:
            return RecommendationOut(
                kind="course_review",
                title=course_review.title,
                reason="Você concluiu as aulas da unidade; agora consolide o bloco.",
                href=(
                    f"/cursos/{course.slug}/unidades/{unit.slug}/checkpoint"
                ),
                estimated_minutes=course_review.estimated_minutes,
                course_slug=course.slug,
            )

    next_lesson = (
        await session.execute(
            select(Lesson)
            .join(Course, Lesson.course_id == Course.id)
            .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
            .where(Lesson.id.not_in(studied_lesson_ids))
            .order_by(Course.position, CourseUnit.position, Lesson.position)
            .limit(1)
        )
    ).scalar_one_or_none()
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
        href="/caderno",
        estimated_minutes=10,
    )


@router.get("/today", response_model=TodayOut)
async def painel_hoje(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TodayOut:
    now = datetime.now(UTC)
    due_reviews = (
        await session.execute(
            select(func.count())
            .select_from(ReviewItem)
            .where(
                ReviewItem.user_id == usuario.id,
                ReviewItem.status == "active",
                ReviewItem.due_at <= now,
            )
        )
    ).scalar_one()
    latest = (
        await session.execute(
            select(StudySessionProgress, Lesson)
            .join(Lesson, StudySessionProgress.lesson_id == Lesson.id)
            .where(StudySessionProgress.user_id == usuario.id)
            .order_by(StudySessionProgress.updated_at.desc())
            .limit(1)
        )
    ).one_or_none()
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    seconds = (
        await session.execute(
            select(func.coalesce(func.sum(StudySessionProgress.total_seconds), 0)).where(
                StudySessionProgress.user_id == usuario.id,
                StudySessionProgress.updated_at >= week_start,
            )
        )
    ).scalar_one()
    recent = None
    if latest is not None:
        study, lesson = latest
        recent = RecentSessionOut(
            course_slug=lesson.course_slug,
            lesson_number=lesson.number,
            lesson_title=lesson.title,
            current_step=study.current_step,
            completed_steps=len(study.completed_steps),
            total_minutes=max(0, round(study.total_seconds / 60)),
            updated_at=study.updated_at,
        )
    return TodayOut(
        recommendation=await _recommendation(session, usuario.id, due_reviews),
        plan=_plan_out(await _stored_plan(session, usuario.id)),
        recorded_minutes_this_week=max(0, round(int(seconds) / 60)),
        recent_session=recent,
    )


@router.get("/skills", response_model=list[SkillSummaryOut])
async def minhas_competencias(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
) -> list[SkillSummaryOut]:
    def scoped_ids(stmt: Select[int]) -> Select[int]:
        scoped = stmt
        if course is not None:
            scoped = scoped.where(Course.slug == course)
        if unit is not None:
            scoped = scoped.where(CourseUnit.slug == unit)
        return scoped

    exercise_ids = scoped_ids(
        select(ExerciseAttempt.id)
        .join(Exercise, ExerciseAttempt.exercise_id == Exercise.id)
        .join(Lesson, Exercise.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
    )
    speaking_ids = scoped_ids(
        select(SpeakingAttempt.id)
        .join(TranscriptCue, SpeakingAttempt.transcript_cue_id == TranscriptCue.id)
        .join(LessonMedia, TranscriptCue.media_id == LessonMedia.id)
        .join(Lesson, LessonMedia.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
    )
    writing_ids = scoped_ids(
        select(WritingFeedbackRecord.id)
        .join(WritingPrompt, WritingFeedbackRecord.prompt_id == WritingPrompt.id)
        .join(Lesson, WritingPrompt.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
    )
    scope_filter = or_(
        and_(
            SkillEvidence.source_type == "exercise_attempt",
            SkillEvidence.source_id.in_(exercise_ids),
        ),
        and_(
            SkillEvidence.source_type == "speaking_attempt",
            SkillEvidence.source_id.in_(speaking_ids),
        ),
        and_(
            SkillEvidence.source_type == "writing_feedback",
            SkillEvidence.source_id.in_(writing_ids),
        ),
    )
    aggregates = (
        await session.execute(
            select(
                SkillEvidence.skill,
                func.count(SkillEvidence.id),
                func.avg(SkillEvidence.score),
            )
            .where(SkillEvidence.user_id == usuario.id, scope_filter)
            .group_by(SkillEvidence.skill)
        )
    ).all()
    by_skill = {skill: (int(samples), float(score)) for skill, samples, score in aggregates}

    topic_stmt = (
        select(
            Exercise.skill,
            Lesson.grammar_tag,
            func.count(ExerciseAttempt.id),
            func.avg(cast(ExerciseAttempt.correct, Integer)),
        )
        .join(Exercise, ExerciseAttempt.exercise_id == Exercise.id)
        .join(Lesson, Exercise.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(ExerciseAttempt.user_id == usuario.id)
    )
    if course is not None:
        topic_stmt = topic_stmt.where(Course.slug == course)
    if unit is not None:
        topic_stmt = topic_stmt.where(CourseUnit.slug == unit)
    topic_rows = (
        await session.execute(topic_stmt.group_by(Exercise.skill, Lesson.grammar_tag))
    ).all()
    fragile: dict[str, list[str]] = {}
    for skill, topic, samples, score in topic_rows:
        if int(samples) >= 2 and float(score) < 0.7:
            fragile.setdefault(skill, []).append(topic)

    result: list[SkillSummaryOut] = []
    for skill, label in SKILL_LABELS.items():
        samples, score = by_skill.get(skill, (0, 0.0))
        percentage = round(score * 100) if samples >= 3 else None
        state: Literal["insufficient", "developing", "steady", "strong"]
        if percentage is None:
            state = "insufficient"
        elif percentage < 60:
            state = "developing"
        elif percentage < 85:
            state = "steady"
        else:
            state = "strong"
        result.append(
            SkillSummaryOut(
                skill=skill,
                label=label,
                samples=samples,
                score_percent=percentage,
                status=state,
                fragile_topics=fragile.get(skill, [])[:2],
            )
        )
    return result
