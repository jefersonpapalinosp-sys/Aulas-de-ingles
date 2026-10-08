"""O seed precisa poder rodar quantas vezes for preciso."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Exercise,
    ExerciseAnswer,
    ExerciseHint,
    Lesson,
    LessonMedia,
    TranscriptCue,
    VocabItem,
    WritingPrompt,
)
from app.db.seed import load_seed, seed_lessons


async def _contagens(session: AsyncSession) -> dict[str, int]:
    saida = {}
    for nome, modelo in (
        ("lesson", Lesson),
        ("lesson_media", LessonMedia),
        ("transcript_cue", TranscriptCue),
        ("vocab_item", VocabItem),
        ("exercise", Exercise),
        ("exercise_answer", ExerciseAnswer),
        ("exercise_hint", ExerciseHint),
        ("writing_prompt", WritingPrompt),
    ):
        saida[nome] = (await session.execute(select(func.count()).select_from(modelo))).scalar_one()
    return saida


@pytest.mark.asyncio
async def test_arquivo_de_seed_tem_as_dez_aulas() -> None:
    dados = load_seed()
    assert [d["number"] for d in dados] == list(range(31, 41))
    assert sum(len(d["vocab"]) for d in dados) == 115
    assert sum(len(d["exercises"]) for d in dados) == 65
    assert sum(len(e.get("hints", [])) for d in dados for e in d["exercises"]) == 18
    assert sum(len(d.get("media", [])) for d in dados) == 1
    assert sum(len(d.get("writing_prompts", [])) for d in dados) == 1
    assert sum(len(m.get("cues", [])) for d in dados for m in d.get("media", [])) == 11


@pytest.mark.asyncio
async def test_seed_rodado_de_novo_nao_duplica(session: AsyncSession) -> None:
    antes = await _contagens(session)
    assert antes["lesson"] == 10

    await seed_lessons(session)

    depois = await _contagens(session)
    assert depois == antes


@pytest.mark.asyncio
async def test_ids_de_vocabulario_sobrevivem_ao_reseed(session: AsyncSession) -> None:
    """A S4 vai pendurar cartas de revisão nesses ids — eles não podem trocar."""
    antes = {
        (v.lesson_id, v.term): v.id for v in (await session.execute(select(VocabItem))).scalars()
    }
    await seed_lessons(session)
    depois = {
        (v.lesson_id, v.term): v.id for v in (await session.execute(select(VocabItem))).scalars()
    }
    assert antes == depois


@pytest.mark.asyncio
async def test_exercicio_com_mais_de_uma_resposta_certa(session: AsyncSession) -> None:
    """`should` e `ought to` precisam valer igual — por isso a tabela separada."""
    lesson = (await session.execute(select(Lesson).where(Lesson.number == 31))).scalar_one()
    exercicio = next(e for e in lesson.exercises if e.position == 3)
    valores = {a.value for a in exercicio.answers}
    assert valores == {"should", "ought to"}
