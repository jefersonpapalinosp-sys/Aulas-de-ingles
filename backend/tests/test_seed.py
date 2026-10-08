"""O seed precisa poder rodar quantas vezes for preciso."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ContentSource,
    Exercise,
    ExerciseAnswer,
    ExerciseHint,
    Lesson,
    LessonMedia,
    LessonVersion,
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
        ("content_source", ContentSource),
        ("lesson_version", LessonVersion),
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
    assert sum(len(d["exercises"]) for d in dados) == 66
    assert sum(len(e.get("hints", [])) for d in dados for e in d["exercises"]) == 19
    assert sum(len(d.get("media", [])) for d in dados) == 2
    assert sum(len(d.get("writing_prompts", [])) for d in dados) == 1
    assert sum(len(m.get("cues", [])) for d in dados for m in d.get("media", [])) == 15
    assert all(d["editorial_status"] == "reviewed" for d in dados)
    assert all(d["learning_strategy"] for d in dados)


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
async def test_ids_de_midia_e_trechos_sobrevivem_ao_reseed(session: AsyncSession) -> None:
    """Retomada e speaking apontam para esses IDs e não podem ser apagados pelo seed."""
    media_before = {
        (item.lesson_id, item.position): item.id
        for item in (await session.execute(select(LessonMedia))).scalars()
    }
    cues_before = {
        (item.media_id, item.position): item.id
        for item in (await session.execute(select(TranscriptCue))).scalars()
    }

    await seed_lessons(session)

    media_after = {
        (item.lesson_id, item.position): item.id
        for item in (await session.execute(select(LessonMedia))).scalars()
    }
    cues_after = {
        (item.media_id, item.position): item.id
        for item in (await session.execute(select(TranscriptCue))).scalars()
    }
    assert media_after == media_before
    assert cues_after == cues_before


@pytest.mark.asyncio
async def test_exercicio_com_mais_de_uma_resposta_certa(session: AsyncSession) -> None:
    """`should` e `ought to` precisam valer igual — por isso a tabela separada."""
    lesson = (await session.execute(select(Lesson).where(Lesson.number == 31))).scalar_one()
    exercicio = next(e for e in lesson.exercises if e.position == 3)
    valores = {a.value for a in exercicio.answers}
    assert valores == {"should", "ought to"}
