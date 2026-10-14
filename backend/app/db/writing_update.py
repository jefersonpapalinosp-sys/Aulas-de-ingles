"""Atualização direcionada de rubricas, preservando IDs, conteúdo e evidências."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Course, Lesson, WritingPrompt
from app.db.seed import load_seed, validate_writing_prompts
from app.domain.writing_rubric import WritingRequirement


async def update_writing_rubrics(session: AsyncSession) -> int:
    lessons = load_seed()
    validate_writing_prompts(lessons)
    rows = (
        await session.execute(
            select(Course.slug, Lesson.number, WritingPrompt)
            .join(Lesson, Lesson.course_id == Course.id)
            .join(WritingPrompt, WritingPrompt.lesson_id == Lesson.id)
        )
    ).all()
    stored = {(course, number, prompt.position): prompt for course, number, prompt in rows}
    changes = []
    for lesson in lessons:
        for raw in lesson["writing_prompts"]:
            key = (lesson["course_slug"], lesson["number"], raw["position"])
            if key not in stored:
                raise ValueError("Catálogo diverge; rubricas não foram aplicadas.")
            prompt = stored[key]
            # Não sobrescrever uma proposta editorial diferente por coincidência de ID.
            if any(
                getattr(prompt, field) != raw[field]
                for field in ("title", "instructions", "min_words", "min_sentences")
            ):
                raise ValueError("Proposta diverge; preserve edição local e revise o rollout.")
            changes.append((prompt, raw))
    for prompt, raw in changes:
        prompt.requirements = [
            WritingRequirement.model_validate(r).model_dump() for r in raw["requirements"]
        ]
    await session.commit()
    return len(changes)
