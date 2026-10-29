"""Agrega evidências de competência dentro de um curso/unidade.

O escopo é resolvido pela origem normalizada da evidência. Isso evita que uma
evidência de outro curso apareça no resumo mesmo quando os cursos reutilizam o
mesmo número de aula.
"""

from typing import Literal

from sqlalchemy import Integer, Select, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Course,
    CourseUnit,
    DialogueTurn,
    Exercise,
    ExerciseAttempt,
    Lesson,
    LessonMedia,
    SkillEvidence,
    SpeakingAttempt,
    SpeakingDialogue,
    TranscriptCue,
    WritingFeedbackRecord,
    WritingPrompt,
)
from app.schemas.dashboard import SkillEvidenceSourceOut, SkillSummaryOut

SKILL_LABELS = {
    "grammar": "Gramática",
    "listening": "Compreensão oral",
    "writing": "Escrita",
    "speaking": "Fala",
}


async def skill_summaries(
    session: AsyncSession,
    user_id: int,
    course_slug: str | None = None,
    unit_slug: str | None = None,
) -> list[SkillSummaryOut]:
    """Devolve as quatro competências, inclusive quando ainda não há amostra."""
    if unit_slug is not None and course_slug is None:
        raise ValueError("course_slug is required when unit_slug is provided")

    def scoped_ids(stmt: Select[int]) -> Select[int]:
        scoped = stmt.where(
            Course.status == "published",
            CourseUnit.status == "published",
        )
        if course_slug is not None:
            scoped = scoped.where(Course.slug == course_slug)
        if unit_slug is not None:
            scoped = scoped.where(CourseUnit.slug == unit_slug)
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
    dialogue_ids = scoped_ids(
        select(DialogueTurn.id)
        .join(SpeakingDialogue, DialogueTurn.dialogue_id == SpeakingDialogue.id)
        .join(Lesson, SpeakingDialogue.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
    )
    scope_filter = or_(
        and_(
            SkillEvidence.source_type == "dialogue_turn", SkillEvidence.source_id.in_(dialogue_ids)
        ),
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
                func.min(SkillEvidence.occurred_at),
                func.max(SkillEvidence.occurred_at),
            )
            .where(SkillEvidence.user_id == user_id, scope_filter)
            .group_by(SkillEvidence.skill)
        )
    ).all()
    by_skill = {
        skill: (int(samples), float(score), period_start, period_end)
        for skill, samples, score, period_start, period_end in aggregates
    }
    source_rows = (
        await session.execute(
            select(
                SkillEvidence.skill,
                SkillEvidence.source_type,
                func.count(SkillEvidence.id),
            )
            .where(SkillEvidence.user_id == user_id, scope_filter)
            .group_by(SkillEvidence.skill, SkillEvidence.source_type)
            .order_by(SkillEvidence.skill, SkillEvidence.source_type)
        )
    ).all()
    sources_by_skill: dict[str, list[SkillEvidenceSourceOut]] = {}
    for skill, source_type, samples in source_rows:
        sources_by_skill.setdefault(skill, []).append(
            SkillEvidenceSourceOut(source_type=source_type, samples=int(samples))
        )

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
        .where(
            ExerciseAttempt.user_id == user_id,
            Course.status == "published",
            CourseUnit.status == "published",
        )
    )
    if course_slug is not None:
        topic_stmt = topic_stmt.where(Course.slug == course_slug)
    if unit_slug is not None:
        topic_stmt = topic_stmt.where(CourseUnit.slug == unit_slug)
    topic_rows = (
        await session.execute(topic_stmt.group_by(Exercise.skill, Lesson.grammar_tag))
    ).all()
    fragile: dict[str, list[str]] = {}
    for skill, topic, samples, score in topic_rows:
        if int(samples) >= 2 and float(score) < 0.7:
            fragile.setdefault(skill, []).append(topic)

    result: list[SkillSummaryOut] = []
    for skill, label in SKILL_LABELS.items():
        samples, score, period_start, period_end = by_skill.get(skill, (0, 0.0, None, None))
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
                period_start=period_start,
                period_end=period_end,
                sources=sources_by_skill.get(skill, []),
                score_percent=percentage,
                status=state,
                fragile_topics=fragile.get(skill, [])[:2],
            )
        )
    return result
