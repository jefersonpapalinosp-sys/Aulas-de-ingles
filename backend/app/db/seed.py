"""Carga do conteúdo das aulas a partir de seed/lessons.json.

Idempotente por construção: rodar duas vezes seguidas não muda contagem
nenhuma. A estratégia difere por tabela, e a razão é a S3/S4:

- `lesson`, `vocab_item` e `exercise` são atualizados no lugar (upsert pela
  chave natural), porque tentativas e cartas de revisão vão apontar para eles
  e não podem perder a referência a cada novo seed.
- O resto é conteúdo puramente descritivo: apagar e reinserir é mais simples
  e não quebra nada.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Exercise,
    ExerciseAnswer,
    GrammarBlock,
    GrammarRow,
    Lesson,
    LessonGoal,
    Phrase,
    PronunciationNote,
    VocabItem,
)

log = logging.getLogger(__name__)


def find_seed_file() -> Path:
    """Localiza seed/lessons.json.

    Sobe a árvore a partir deste módulo até achar. Funciona tanto rodando no
    host (raiz do repo) quanto dentro do container (onde seed/ é montado em
    /app/seed). SEED_FILE no ambiente vence tudo.
    """
    if env := os.getenv("SEED_FILE"):
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "seed" / "lessons.json"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("seed/lessons.json não encontrado — defina SEED_FILE.")


def load_seed(path: Path | None = None) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((path or find_seed_file()).read_text(encoding="utf-8"))
    return data


async def _upsert_lesson(session: AsyncSession, raw: dict[str, Any]) -> Lesson:
    lesson = (
        await session.execute(select(Lesson).where(Lesson.number == raw["number"]))
    ).scalar_one_or_none()
    if lesson is None:
        lesson = Lesson(number=raw["number"])
        session.add(lesson)
    lesson.title = raw["title"]
    lesson.title_pt = raw["title_pt"]
    lesson.voa_url = raw["voa_url"]
    lesson.grammar_tag = raw["grammar_tag"]
    lesson.focus_points = raw["focus_points"]
    lesson.story_note = raw["story_note"]
    lesson.lead = raw["lead"]
    await session.flush()
    return lesson


async def _replace_descriptive(session: AsyncSession, lesson: Lesson, raw: dict[str, Any]) -> None:
    """Objetivos, gramática, frases e pronúncia: apaga e reinsere."""
    for model in (LessonGoal, GrammarBlock, Phrase, PronunciationNote):
        await session.execute(delete(model).where(model.lesson_id == lesson.id))
    await session.flush()

    for i, g in enumerate(raw["goals"]):
        session.add(LessonGoal(lesson_id=lesson.id, position=i, text=g))

    for b in raw["grammar_blocks"]:
        block = GrammarBlock(
            lesson_id=lesson.id,
            position=b["position"],
            heading=b["heading"],
            why=b["why"],
            warning=b["warning"],
            table_head=b["table_head"],
        )
        session.add(block)
        await session.flush()
        for r in b["rows"]:
            session.add(GrammarRow(block_id=block.id, position=r["position"], cells=r["cells"]))

    for p in raw["phrases"]:
        session.add(
            Phrase(
                lesson_id=lesson.id,
                position=p["position"],
                text_en=p["text_en"],
                text_pt=p["text_pt"],
                note=p["note"],
            )
        )

    for n in raw["pronunciation"]:
        session.add(
            PronunciationNote(
                lesson_id=lesson.id,
                position=n["position"],
                label=n["label"],
                explanation=n["explanation"],
            )
        )


async def _upsert_vocab(session: AsyncSession, lesson: Lesson, raw: dict[str, Any]) -> None:
    """Upsert por (lesson_id, term); some o que saiu do seed."""
    existentes = {
        v.term: v
        for v in (
            await session.execute(select(VocabItem).where(VocabItem.lesson_id == lesson.id))
        ).scalars()
    }
    vistos: set[str] = set()
    for v in raw["vocab"]:
        item = existentes.get(v["term"])
        if item is None:
            item = VocabItem(lesson_id=lesson.id, term=v["term"])
            session.add(item)
        item.position = v["position"]
        item.ipa = v["ipa"]
        item.translation_pt = v["translation_pt"]
        item.example_en = v["example_en"]
        vistos.add(v["term"])
    for term, item in existentes.items():
        if term not in vistos:
            await session.delete(item)
    await session.flush()


async def _upsert_exercises(session: AsyncSession, lesson: Lesson, raw: dict[str, Any]) -> None:
    """Upsert por (lesson_id, position); as respostas são substituídas."""
    existentes = {
        e.position: e
        for e in (
            await session.execute(select(Exercise).where(Exercise.lesson_id == lesson.id))
        ).scalars()
    }
    vistas: set[int] = set()
    for e in raw["exercises"]:
        ex = existentes.get(e["position"])
        if ex is None:
            ex = Exercise(lesson_id=lesson.id, position=e["position"])
            session.add(ex)
        ex.prompt = e["prompt"]
        ex.hint = e["hint"]
        ex.explanation = e["explanation"]
        await session.flush()
        await session.execute(delete(ExerciseAnswer).where(ExerciseAnswer.exercise_id == ex.id))
        for i, value in enumerate(e["answers"]):
            session.add(ExerciseAnswer(exercise_id=ex.id, position=i, value=value))
        vistas.add(e["position"])
    for position, ex in existentes.items():
        if position not in vistas:
            await session.delete(ex)
    await session.flush()


async def seed_lessons(session: AsyncSession, path: Path | None = None) -> int:
    """Aplica o seed e devolve quantas aulas foram processadas."""
    dados = load_seed(path)
    for raw in dados:
        lesson = await _upsert_lesson(session, raw)
        await _replace_descriptive(session, lesson, raw)
        await _upsert_vocab(session, lesson, raw)
        await _upsert_exercises(session, lesson, raw)
    await session.commit()
    log.info("seed aplicado: %d aulas", len(dados))
    return len(dados)
