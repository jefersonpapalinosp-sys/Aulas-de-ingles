"""Evidência e revisão derivadas de turnos concluídos, na mesma transação.

Só checks determinísticos alimentam a evidência. Cartas contêm o vocabulário
editorial, nunca a transcrição do aluno nem a resposta do provedor.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Course,
    CourseUnit,
    DialogueTurn,
    Lesson,
    LessonProgress,
    ReviewItem,
    SkillEvidence,
    SpeakingDialogue,
    VocabItem,
)
from app.schemas.dashboard import RecommendationOut
from app.schemas.dialogue import DialogueCheckDetails


async def record_learning(
    session: AsyncSession,
    dialogue: SpeakingDialogue,
    turn: DialogueTurn,
) -> None:
    """Chamador mantém o lock do diálogo até o commit, serializando os turnos."""
    if turn.role != "student" or turn.state != "completed" or not turn.checks:
        return
    await session.execute(
        insert(SkillEvidence)
        .values(
            user_id=dialogue.user_id,
            skill="speaking",
            source_type="dialogue_turn",
            source_id=turn.id,
            score=sum(value is True for value in turn.checks.values()) / len(turn.checks),
            occurred_at=turn.completed_at,
        )
        .on_conflict_do_nothing(constraint="uq_skill_evidence_source")
    )
    failed_details = (
        await session.execute(
            select(DialogueTurn.check_details).where(
                DialogueTurn.dialogue_id == dialogue.id,
                DialogueTurn.role == "student",
                DialogueTurn.state == "completed",
                DialogueTurn.checks["target_terms_missing"].as_boolean().is_(False),
            )
        )
    ).scalars()
    # Sem backfill: um turno antigo sem recorte não prova a ausência de um
    # termo do conteúdo atual. Cada turno novo conserva sua própria expectativa.
    missed = Counter(
        term
        for details in failed_details
        if details is not None
        for term in {
            item.text
            for item in DialogueCheckDetails.model_validate(details).target_terms
            if not item.covered
        }
    )
    repeated = [term for term, count in missed.items() if count >= 2]
    if not repeated:
        return
    vocabulary = (
        await session.execute(
            select(VocabItem).where(
                VocabItem.lesson_id == dialogue.lesson_id, VocabItem.term.in_(repeated)
            )
        )
    ).scalars()
    for item in vocabulary:
        # Uma carta por termo e diálogo. Reprocessar preserva o agendamento,
        # a suspensão e a revisão que o aluno já fez.
        await session.execute(
            insert(ReviewItem)
            .values(
                user_id=dialogue.user_id,
                lesson_id=dialogue.lesson_id,
                vocab_item_id=item.id,
                item_type="speaking_prompt",
                source_type="dialogue_turn",
                source_id=turn.id,
                source_key=f"dialogue:{dialogue.id}:vocab:{item.id}",
                skill="speaking",
                prompt=f'Crie uma frase em inglês usando "{item.term}".',
                prompt_note=item.ipa,
                answer=item.translation_pt,
                context=item.example_en,
                origin_reason="dialogue_missed_term",
                estimated_seconds=60,
                due_at=turn.completed_at,
            )
            .on_conflict_do_nothing(constraint="uq_review_item_user_source")
        )


async def conversation_recommendation(
    session: AsyncSession, user_id: int, course: Course, now: datetime | None = None
) -> RecommendationOut | None:
    """Aula estudada sem conversa iniciada nos últimos sete dias, no curso atual."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=7)
    recent = (
        select(SpeakingDialogue.id)
        .where(
            SpeakingDialogue.user_id == user_id,
            SpeakingDialogue.lesson_id == Lesson.id,
            SpeakingDialogue.started_at >= cutoff,
        )
        .correlate(Lesson)
        .exists()
    )
    number = await session.scalar(
        select(Lesson.number)
        .join(LessonProgress, LessonProgress.lesson_id == Lesson.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            LessonProgress.user_id == user_id,
            Lesson.course_id == course.id,
            CourseUnit.status == "published",
            ~recent,
        )
        .order_by(CourseUnit.position, Lesson.position, Lesson.id)
        .limit(1)
    )
    if number is None:
        return None
    return RecommendationOut(
        kind="conversation",
        title=f"Praticar a conversa da Aula {number}",
        reason="Você já estudou esta aula e não iniciou uma conversa nela nos últimos 7 dias.",
        href=f"/cursos/{course.slug}/aulas/{number}/estudar/revisar#conversa",
        estimated_minutes=10,
        course_slug=course.slug,
        lesson_number=number,
    )
