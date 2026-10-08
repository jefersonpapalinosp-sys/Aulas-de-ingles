"""Carga do conteúdo das aulas a partir de seed/lessons.json.

Idempotente por construção: rodar duas vezes seguidas não muda contagem
nenhuma. A estratégia difere por tabela, e a razão é a S3/S4:

- `lesson`, `vocab_item`, `exercise` e `writing_prompt` são atualizados no
  lugar (upsert pela chave natural), porque dados do usuário vão apontar para
  eles e não podem perder a referência a cada novo seed.
- O resto é conteúdo puramente descritivo: apagar e reinserir é mais simples
  e não quebra nada.
"""

import json
import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ContentSource,
    Course,
    CourseReview,
    CourseReviewQuestion,
    CourseUnit,
    Exercise,
    ExerciseAnswer,
    ExerciseHint,
    GrammarBlock,
    GrammarRow,
    Lesson,
    LessonGoal,
    LessonMedia,
    LessonVersion,
    Phrase,
    PronunciationNote,
    TranscriptCue,
    VocabItem,
    WritingPrompt,
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


def load_course_seed(path: Path | None = None) -> list[dict[str, Any]]:
    if path is None:
        if env := os.getenv("COURSE_SEED_FILE"):
            path = Path(env)
        else:
            path = find_seed_file().with_name("courses.json")
    data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return data


def validate_course_reviews(
    courses: list[dict[str, Any]], lessons: list[dict[str, Any]]
) -> None:
    """Falha cedo quando um checkpoint referencia conteúdo inexistente/inválido."""
    lessons_by_course_number = {
        (str(lesson["course_slug"]), int(lesson["number"])): lesson
        for lesson in lessons
    }
    for course in courses:
        course_slug = str(course["slug"])
        for unit in course["units"]:
            review = unit.get("review")
            if review is None:
                continue

            listening_number = review.get("listening_lesson_number")
            listening_position = review.get("listening_media_position")
            if (listening_number is None) != (listening_position is None):
                raise ValueError(
                    f"Checkpoint {course_slug}/{unit['slug']} deve informar aula e posição "
                    "de listening juntas."
                )

            referenced_numbers = {int(review["review_lesson_number"])}
            if listening_number is not None:
                referenced_numbers.add(int(listening_number))
            questions = review.get("questions", [])
            if not questions:
                raise ValueError(
                    f"Checkpoint {course_slug}/{unit['slug']} precisa ter questões."
                )
            positions = [int(question["position"]) for question in questions]
            if positions != list(range(1, len(questions) + 1)):
                raise ValueError(
                    f"Checkpoint {course_slug}/{unit['slug']} tem posições não contíguas."
                )

            for question in questions:
                answers = question.get("accepted_answers", [])
                if not answers or not all(
                    isinstance(answer, str) and answer.strip() for answer in answers
                ):
                    raise ValueError(
                        f"Questão {question['position']} de {course_slug}/{unit['slug']} "
                        "precisa de resposta aceita."
                    )
                options = question.get("options")
                if question["activity_type"] == "multiple_choice" and (
                    not options or not set(answers).issubset(set(options))
                ):
                    raise ValueError(
                        f"Questão {question['position']} de {course_slug}/{unit['slug']} "
                        "tem gabarito fora das alternativas."
                    )
                lesson_numbers = question.get("lesson_numbers", [])
                if not lesson_numbers:
                    raise ValueError(
                        f"Questão {question['position']} de {course_slug}/{unit['slug']} "
                        "precisa referenciar ao menos uma aula."
                    )
                referenced_numbers.update(int(number) for number in lesson_numbers)

            for number in referenced_numbers:
                if (course_slug, number) not in lessons_by_course_number:
                    raise ValueError(
                        f"Checkpoint {course_slug}/{unit['slug']} referencia a Aula {number} "
                        "fora do curso semeado."
                    )

            if listening_number is not None:
                listening_lesson = lessons_by_course_number[(course_slug, int(listening_number))]
                media_positions = {
                    int(media["position"]) for media in listening_lesson.get("media", [])
                }
                if int(listening_position) not in media_positions:
                    raise ValueError(
                        f"Checkpoint {course_slug}/{unit['slug']} referencia mídia inexistente "
                        f"na Aula {listening_number}."
                    )


async def _upsert_catalog(session: AsyncSession, courses: list[dict[str, Any]]) -> None:
    """Cria cursos e unidades antes das aulas que dependem deles."""
    for raw in courses:
        course = (
            await session.execute(select(Course).where(Course.slug == raw["slug"]))
        ).scalar_one_or_none()
        if course is None:
            course = Course(slug=raw["slug"])
            session.add(course)
        course.title = raw["title"]
        course.level = raw["level"]
        course.proficiency_label = raw["proficiency_label"]
        course.provider = raw["provider"]
        course.source_url = raw["source_url"]
        course.position = raw["position"]
        course.status = raw["status"]
        course.total_lessons = raw["total_lessons"]
        await session.flush()

        existing_units = {
            unit.slug: unit
            for unit in (
                await session.execute(
                    select(CourseUnit).where(CourseUnit.course_id == course.id)
                )
            ).scalars()
        }
        for raw_unit in raw["units"]:
            unit = existing_units.get(raw_unit["slug"])
            if unit is None:
                unit = CourseUnit(course_id=course.id, slug=raw_unit["slug"])
                session.add(unit)
            unit.title = raw_unit["title"]
            unit.position = raw_unit["position"]
            unit.status = raw_unit["status"]
            unit.lesson_start = raw_unit["lesson_start"]
            unit.lesson_end = raw_unit["lesson_end"]
            unit.total_lessons = raw_unit["total_lessons"]
            await session.flush()
            if raw_review := raw_unit.get("review"):
                await _upsert_course_review(session, unit, raw_review)
        await session.flush()


async def _upsert_course_review(
    session: AsyncSession, unit: CourseUnit, raw: dict[str, Any]
) -> None:
    """Atualiza checkpoint e questões sem trocar suas chaves estáveis."""
    review = (
        await session.execute(select(CourseReview).where(CourseReview.unit_id == unit.id))
    ).scalar_one_or_none()
    if review is None:
        review = CourseReview(unit_id=unit.id, slug=raw["slug"])
        session.add(review)
    review.slug = raw["slug"]
    review.title = raw["title"]
    review.position = raw["position"]
    review.status = raw["status"]
    review.source_kind = raw["source_kind"]
    review.source_title = raw["source_title"]
    review.source_url = raw.get("source_url")
    review.source_note = raw["source_note"]
    review.intro = raw["intro"]
    review.estimated_minutes = raw["estimated_minutes"]
    review.content_version = raw["content_version"]
    review.review_lesson_number = raw["review_lesson_number"]
    review.listening_lesson_number = raw.get("listening_lesson_number")
    review.listening_media_position = raw.get("listening_media_position")
    await session.flush()

    existing = {
        question.position: question
        for question in (
            await session.execute(
                select(CourseReviewQuestion).where(CourseReviewQuestion.review_id == review.id)
            )
        ).scalars()
    }
    seen: set[int] = set()
    for raw_question in raw["questions"]:
        position = int(raw_question["position"])
        question = existing.get(position)
        if question is None:
            question = CourseReviewQuestion(review_id=review.id, position=position)
            session.add(question)
        question.activity_type = raw_question["activity_type"]
        question.skill = raw_question["skill"]
        question.prompt = raw_question["prompt"]
        question.options = raw_question.get("options")
        question.accepted_answers = raw_question["accepted_answers"]
        question.explanation = raw_question["explanation"]
        question.lesson_numbers = raw_question["lesson_numbers"]
        seen.add(position)
    for position, question in existing.items():
        if position not in seen:
            await session.delete(question)
    await session.flush()


async def _upsert_lesson(session: AsyncSession, raw: dict[str, Any]) -> Lesson:
    course_slug = str(raw["course_slug"])
    unit_slug = str(raw["unit_slug"])
    course = (
        await session.execute(select(Course).where(Course.slug == course_slug))
    ).scalar_one_or_none()
    if course is None:
        raise ValueError(f"Curso {course_slug!r} não existe no catálogo.")
    unit = (
        await session.execute(
            select(CourseUnit).where(
                CourseUnit.course_id == course.id,
                CourseUnit.slug == unit_slug,
            )
        )
    ).scalar_one_or_none()
    if unit is None:
        raise ValueError(f"Unidade {course_slug}/{unit_slug} não existe no catálogo.")
    lesson = (
        await session.execute(
            select(Lesson).where(
                Lesson.course_id == course.id,
                Lesson.number == raw["number"],
            )
        )
    ).scalar_one_or_none()
    if lesson is None:
        lesson = Lesson(course_id=course.id, unit_id=unit.id, number=raw["number"])
        session.add(lesson)
    lesson.course_id = course.id
    lesson.unit_id = unit.id
    lesson.slug = raw["slug"]
    lesson.position = raw["position"]
    lesson.title = raw["title"]
    lesson.title_pt = raw["title_pt"]
    lesson.voa_url = raw["voa_url"]
    lesson.grammar_tag = raw["grammar_tag"]
    lesson.focus_points = raw["focus_points"]
    lesson.story_note = raw["story_note"]
    lesson.lead = raw["lead"]
    lesson.warmup_prompt = raw["warmup_prompt"]
    lesson.listening_focus = raw["listening_focus"]
    await session.flush()
    return lesson


async def _sync_editorial(session: AsyncSession, lesson: Lesson, raw: dict[str, Any]) -> None:
    """Mantém origem e versão explícitas sem apagar versões anteriores."""
    source_specs: tuple[tuple[str, str, str, str | None, str], ...] = (
        (
            "official",
            f"VOA Let's Learn English — Lesson {lesson.number}",
            "VOA Learning English",
            str(raw["voa_url"]),
            (
                "Texto e MP3 da VOA Learning English em domínio público, com crédito à fonte; "
                "materiais identificados como provenientes de agências terceiras não se incluem."
            ),
        ),
        (
            "authorial",
            "Explicações e atividades do Aulas de Inglês",
            "Aulas de Inglês",
            None,
            "Conteúdo autoral do projeto; não substitui a fonte oficial.",
        ),
    )
    existing_sources = {
        item.kind: item
        for item in (
            await session.execute(select(ContentSource).where(ContentSource.lesson_id == lesson.id))
        ).scalars()
    }
    for kind, title, publisher, url, license_note in source_specs:
        source = existing_sources.get(kind)
        if source is None:
            source = ContentSource(lesson_id=lesson.id, kind=kind)
            session.add(source)
        source.title = title
        source.publisher = publisher
        source.url = url
        source.license_note = license_note
        source.accessed_at = date.fromisoformat(raw.get("source_accessed_at", "2026-10-07"))

    version_number = int(raw.get("content_version", 1))
    version = (
        await session.execute(
            select(LessonVersion).where(
                LessonVersion.lesson_id == lesson.id,
                LessonVersion.version == version_number,
            )
        )
    ).scalar_one_or_none()
    if version is None:
        version = LessonVersion(lesson_id=lesson.id, version=version_number)
        session.add(version)
    version.status = raw.get("editorial_status", "reviewed")
    version.learning_strategy = raw["learning_strategy"]
    version.review_note = raw.get(
        "review_note", "Conteúdo revisado contra o plano oficial e adaptado ao piloto."
    )
    version.reviewed_at = datetime(2026, 10, 7, tzinfo=UTC)
    version.published_at = (
        datetime(2026, 10, 7, tzinfo=UTC) if version.status == "published" else None
    )
    await session.flush()


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


async def _upsert_media(session: AsyncSession, lesson: Lesson, raw: dict[str, Any]) -> None:
    """Preserva IDs usados por retomada e gravações ao atualizar a mídia."""
    existing_media = {
        item.position: item
        for item in (
            await session.execute(select(LessonMedia).where(LessonMedia.lesson_id == lesson.id))
        ).scalars()
    }
    seen_media: set[int] = set()
    for raw_media in raw.get("media", []):
        position = int(raw_media["position"])
        media = existing_media.get(position)
        if media is None:
            media = LessonMedia(lesson_id=lesson.id, position=position)
            session.add(media)
        media.kind = raw_media["kind"]
        media.label = raw_media["label"]
        media.source_url = raw_media["source_url"]
        media.license_status = raw_media["license_status"]
        media.license_url = raw_media.get("license_url")
        media.license_note = raw_media["license_note"]
        media.attribution = raw_media["attribution"]
        media.offline_policy = raw_media["offline_policy"]
        media.license_reviewed_at = date.fromisoformat(raw_media["license_reviewed_at"])
        media.duration_seconds = raw_media.get("duration_seconds")
        media.listening_exercise_position = raw_media.get("listening_exercise_position")
        media.transcript = raw_media.get("transcript", [])
        await session.flush()

        existing_cues = {
            cue.position: cue
            for cue in (
                await session.execute(
                    select(TranscriptCue).where(TranscriptCue.media_id == media.id)
                )
            ).scalars()
        }
        seen_cues: set[int] = set()
        for raw_cue in raw_media.get("cues", []):
            cue_position = int(raw_cue["position"])
            cue = existing_cues.get(cue_position)
            if cue is None:
                cue = TranscriptCue(media_id=media.id, position=cue_position)
                session.add(cue)
            cue.start_seconds = raw_cue["start_seconds"]
            cue.end_seconds = raw_cue["end_seconds"]
            cue.speaker = raw_cue["speaker"]
            cue.text_en = raw_cue["text_en"]
            cue.text_pt = raw_cue["text_pt"]
            seen_cues.add(cue_position)
        for cue_position, cue in existing_cues.items():
            if cue_position not in seen_cues:
                await session.delete(cue)
        seen_media.add(position)
    for position, media in existing_media.items():
        if position not in seen_media:
            await session.delete(media)
    await session.flush()


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
        ex.activity_type = e.get("activity_type", "gap_fill")
        ex.skill = e.get("skill", "grammar")
        ex.objective = e.get(
            "objective",
            "listen"
            if ex.skill == "listening"
            else "correct"
            if ex.activity_type == "transformation"
            else "recognize"
            if ex.activity_type == "multiple_choice"
            else "apply",
        )
        ex.options = e.get("options")
        await session.flush()
        await session.execute(delete(ExerciseAnswer).where(ExerciseAnswer.exercise_id == ex.id))
        await session.execute(delete(ExerciseHint).where(ExerciseHint.exercise_id == ex.id))
        for i, value in enumerate(e["answers"]):
            session.add(ExerciseAnswer(exercise_id=ex.id, position=i, value=value))
        for level, content in enumerate(e.get("hints", []), start=1):
            session.add(ExerciseHint(exercise_id=ex.id, level=level, content=content))
        vistas.add(e["position"])
    for position, ex in existentes.items():
        if position not in vistas:
            await session.delete(ex)
    await session.flush()


async def _upsert_writing_prompts(
    session: AsyncSession, lesson: Lesson, raw: dict[str, Any]
) -> None:
    """Upsert por posição para preservar rascunhos e versões do usuário."""
    existentes = {
        prompt.position: prompt
        for prompt in (
            await session.execute(select(WritingPrompt).where(WritingPrompt.lesson_id == lesson.id))
        ).scalars()
    }
    vistas: set[int] = set()
    for item in raw.get("writing_prompts", []):
        prompt = existentes.get(item["position"])
        if prompt is None:
            prompt = WritingPrompt(lesson_id=lesson.id, position=item["position"])
            session.add(prompt)
        prompt.title = item["title"]
        prompt.instructions = item["instructions"]
        prompt.min_words = item["min_words"]
        prompt.min_sentences = item["min_sentences"]
        prompt.requirements = item["requirements"]
        vistas.add(item["position"])
    for position, prompt in existentes.items():
        if position not in vistas:
            await session.delete(prompt)
    await session.flush()


async def seed_lessons(session: AsyncSession, path: Path | None = None) -> int:
    """Aplica o seed e devolve quantas aulas foram processadas."""
    catalog_path = path.with_name("courses.json") if path is not None else None
    courses = load_course_seed(catalog_path)
    dados = load_seed(path)
    validate_course_reviews(courses, dados)
    await _upsert_catalog(session, courses)
    for raw in dados:
        lesson = await _upsert_lesson(session, raw)
        await _sync_editorial(session, lesson, raw)
        await _replace_descriptive(session, lesson, raw)
        await _upsert_media(session, lesson, raw)
        await _upsert_vocab(session, lesson, raw)
        await _upsert_exercises(session, lesson, raw)
        await _upsert_writing_prompts(session, lesson, raw)
    await session.commit()
    log.info("seed aplicado: %d aulas", len(dados))
    return len(dados)
