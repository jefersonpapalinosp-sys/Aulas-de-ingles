"""Painel Hoje: plano leve, recomendação explicada e competências."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from typing import cast as typing_cast

from fastapi import APIRouter, Body, Depends
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.models import (
    Exercise,
    ExerciseAttempt,
    Lesson,
    LessonProgress,
    ReviewItem,
    SkillEvidence,
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
            href=f"/aulas/{lesson.number}/estudar/{study.current_step}",
            estimated_minutes=10,
            lesson_number=lesson.number,
        )

    studied_lesson_ids = select(LessonProgress.lesson_id).where(LessonProgress.user_id == user_id)
    next_lesson = (
        await session.execute(
            select(Lesson)
            .where(Lesson.id.not_in(studied_lesson_ids))
            .order_by(Lesson.number)
            .limit(1)
        )
    ).scalar_one_or_none()
    if next_lesson is not None:
        return RecommendationOut(
            kind="start_lesson",
            title=f"Começar a Aula {next_lesson.number}",
            reason="É a próxima aula ainda não concluída na sequência do bloco.",
            href=f"/aulas/{next_lesson.number}/estudar",
            estimated_minutes=20,
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
) -> list[SkillSummaryOut]:
    aggregates = (
        await session.execute(
            select(
                SkillEvidence.skill,
                func.count(SkillEvidence.id),
                func.avg(SkillEvidence.score),
            )
            .where(SkillEvidence.user_id == usuario.id)
            .group_by(SkillEvidence.skill)
        )
    ).all()
    by_skill = {skill: (int(samples), float(score)) for skill, samples, score in aggregates}

    topic_rows = (
        await session.execute(
            select(
                Exercise.skill,
                Lesson.grammar_tag,
                func.count(ExerciseAttempt.id),
                func.avg(cast(ExerciseAttempt.correct, Integer)),
            )
            .join(Exercise, ExerciseAttempt.exercise_id == Exercise.id)
            .join(Lesson, Exercise.lesson_id == Lesson.id)
            .where(ExerciseAttempt.user_id == usuario.id)
            .group_by(Exercise.skill, Lesson.grammar_tag)
        )
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
