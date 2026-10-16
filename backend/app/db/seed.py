"""Carga do conteúdo das aulas a partir de seed/lessons.json.

Sprint 40B.1: prévia somente leitura, reaplicação sem DML e inserção aditiva.
Alterar ou omitir conteúdo existente exige a etapa de versionamento 40B.2;
nenhum histórico deve desaparecer por cascata durante a carga editorial.
"""

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import editorial_identity
from app.db.seed_plan import Graph, apply_graph, preview_graph, seed_graph
from app.domain.answers import parse_classification
from app.domain.writing_rubric import WritingRequirement

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


def validate_writing_prompts(lessons: list[dict[str, Any]]) -> None:
    """Rejeita rubricas inválidas antes de abrir qualquer escrita do seed."""
    for lesson in lessons:
        for prompt in lesson.get("writing_prompts", []):
            try:
                if not prompt["requirements"]:
                    raise ValueError("Proposta sem requisitos.")
                for requirement in prompt["requirements"]:
                    WritingRequirement.model_validate(requirement)
            except ValueError as error:
                raise ValueError(
                    f"Rubrica inválida: {lesson['course_slug']}/{lesson['number']}, "
                    f"proposta {prompt['position']}."
                ) from error


def validate_editorial_provenance(lessons: list[dict[str, Any]]) -> None:
    """Impede que datas de acesso/execução sejam inventadas como revisão."""
    for lesson in lessons:
        reference = f"{lesson.get('course_slug', '?')}/Aula {lesson.get('number', '?')}"
        try:
            accessed_at = date.fromisoformat(lesson["source_accessed_at"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"{reference} precisa de source_accessed_at explícito.") from error
        status = lesson.get("editorial_status")
        if status not in {"draft", "reviewed", "published"}:
            raise ValueError(f"{reference} tem editorial_status inválido.")
        note = lesson.get("review_note")
        if not isinstance(note, str) or not note.strip() or len(note) > 500:
            raise ValueError(f"{reference} precisa de review_note explícita e válida.")

        timestamps: dict[str, datetime | None] = {}
        for field in ("reviewed_at", "published_at"):
            raw = lesson.get(field)
            if raw is None:
                timestamps[field] = None
                continue
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (AttributeError, ValueError) as error:
                raise ValueError(f"{reference} tem {field} inválido.") from error
            if parsed.tzinfo is None:
                raise ValueError(f"{reference} tem {field} sem fuso horário.")
            if field == "reviewed_at" and parsed.date() < accessed_at:
                raise ValueError(f"{reference} foi revisada antes do acesso registrado à fonte.")
            timestamps[field] = parsed
        if timestamps["published_at"] is not None and timestamps["reviewed_at"] is None:
            raise ValueError(f"{reference} tem publicação sem revisão datada.")
        if status == "published" and timestamps["published_at"] is None:
            raise ValueError(f"{reference} publicada precisa de published_at explícito.")
        if (
            timestamps["published_at"] is not None
            and timestamps["reviewed_at"] is not None
            and timestamps["published_at"] < timestamps["reviewed_at"]
        ):
            raise ValueError(f"{reference} foi publicada antes da revisão.")


def load_course_seed(path: Path | None = None) -> list[dict[str, Any]]:
    if path is None:
        if env := os.getenv("COURSE_SEED_FILE"):
            path = Path(env)
        else:
            path = find_seed_file().with_name("courses.json")
    data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return data


def validate_exercises(lessons: list[dict[str, Any]]) -> None:
    """Valida os campos estruturados que não cabem em constraints simples."""
    for lesson in lessons:
        lesson_ref = f"{lesson['course_slug']}/Aula {lesson['number']}"
        for exercise in lesson.get("exercises", []):
            activity_type = exercise.get("activity_type", "gap_fill")
            items = exercise.get("classification_items")
            categories = exercise.get("classification_categories")
            if activity_type != "classification":
                if items is not None or categories is not None:
                    raise ValueError(
                        f"Exercício {exercise['position']} de {lesson_ref} só pode informar "
                        "itens/categorias quando for classification."
                    )
                continue

            if (
                not isinstance(items, list)
                or not items
                or not all(isinstance(item, str) and item.strip() for item in items)
            ):
                raise ValueError(
                    f"Classificação {exercise['position']} de {lesson_ref} precisa de itens."
                )
            if (
                not isinstance(categories, list)
                or len(categories) < 2
                or not all(
                    isinstance(category, str) and category.strip() for category in categories
                )
            ):
                raise ValueError(
                    f"Classificação {exercise['position']} de {lesson_ref} precisa de ao "
                    "menos duas categorias."
                )
            if len({item.strip().casefold() for item in items}) != len(items):
                raise ValueError(
                    f"Classificação {exercise['position']} de {lesson_ref} repete itens."
                )
            if len({category.strip().casefold() for category in categories}) != len(categories):
                raise ValueError(
                    f"Classificação {exercise['position']} de {lesson_ref} repete categorias."
                )

            answers = exercise.get("answers", [])
            if not answers:
                raise ValueError(
                    f"Classificação {exercise['position']} de {lesson_ref} precisa de gabarito."
                )
            for answer in answers:
                assignment = parse_classification(answer) if isinstance(answer, str) else None
                if (
                    assignment is None
                    or set(assignment) != set(items)
                    or any(category not in categories for category in assignment.values())
                ):
                    raise ValueError(
                        f"Classificação {exercise['position']} de {lesson_ref} tem gabarito "
                        "incompatível com os itens e categorias."
                    )


def validate_course_reviews(courses: list[dict[str, Any]], lessons: list[dict[str, Any]]) -> None:
    """Falha cedo quando catálogo ou checkpoint contradizem o conteúdo semeado."""
    lessons_by_course_number = {
        (str(lesson["course_slug"]), int(lesson["number"])): lesson for lesson in lessons
    }
    catalog_units = {
        (str(course["slug"]), str(unit["slug"])) for course in courses for unit in course["units"]
    }
    for lesson in lessons:
        unit_key = (str(lesson["course_slug"]), str(lesson["unit_slug"]))
        if unit_key not in catalog_units:
            raise ValueError(
                f"Aula {lesson['number']} referencia unidade inexistente "
                f"{unit_key[0]}/{unit_key[1]}."
            )

    for course in courses:
        course_slug = str(course["slug"])
        for unit in course["units"]:
            unit_lessons = [
                lesson
                for lesson in lessons
                if lesson["course_slug"] == course_slug and lesson["unit_slug"] == unit["slug"]
            ]
            start = int(unit["lesson_start"])
            end = int(unit["lesson_end"])
            outside = [
                int(lesson["number"])
                for lesson in unit_lessons
                if not start <= int(lesson["number"]) <= end
            ]
            if outside:
                raise ValueError(
                    f"Aula {outside[0]} está fora da faixa {start}–{end} "
                    f"de {course_slug}/{unit['slug']}."
                )
            positions = sorted(int(lesson["position"]) for lesson in unit_lessons)
            if positions != list(range(1, len(unit_lessons) + 1)):
                raise ValueError(
                    f"Unidade {course_slug}/{unit['slug']} tem posições de aula não contíguas."
                )
            expected_lessons = int(unit["total_lessons"])
            if unit["status"] == "published" and course["status"] != "published":
                raise ValueError(
                    f"Unidade publicada {course_slug}/{unit['slug']} pertence a curso "
                    "não publicado."
                )
            if unit["status"] == "published" and len(unit_lessons) != expected_lessons:
                raise ValueError(
                    f"Unidade publicada {course_slug}/{unit['slug']} declara "
                    f"{expected_lessons} aulas, mas possui {len(unit_lessons)}."
                )
            if unit["status"] != "published" and unit_lessons:
                raise ValueError(
                    f"Unidade em preparação {course_slug}/{unit['slug']} não pode "
                    "conter aulas públicas."
                )

            review = unit.get("review")
            if review is None:
                continue
            if unit["status"] != "published":
                raise ValueError(
                    f"Unidade em preparação {course_slug}/{unit['slug']} não pode "
                    "conter checkpoint."
                )

            listening_number = review.get("listening_lesson_number")
            listening_position = review.get("listening_media_position")
            listening_key = review.get("listening_media_key")
            if (listening_number is None) != (
                listening_position is None and listening_key is None
            ):
                raise ValueError(
                    f"Checkpoint {course_slug}/{unit['slug']} deve informar aula e referência "
                    "de listening juntas."
                )

            referenced_numbers = {int(review["review_lesson_number"])}
            if listening_number is not None:
                referenced_numbers.add(int(listening_number))
            questions = review.get("questions", [])
            if not questions:
                raise ValueError(f"Checkpoint {course_slug}/{unit['slug']} precisa ter questões.")
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

            outside_review_range = sorted(
                number for number in referenced_numbers if not start <= number <= end
            )
            if outside_review_range:
                raise ValueError(
                    f"Checkpoint {course_slug}/{unit['slug']} referencia a Aula "
                    f"{outside_review_range[0]} fora da faixa {start}–{end} da unidade."
                )

            for number in referenced_numbers:
                if (course_slug, number) not in lessons_by_course_number:
                    raise ValueError(
                        f"Checkpoint {course_slug}/{unit['slug']} referencia a Aula {number} "
                        "fora do curso semeado."
                    )

            if listening_number is not None:
                listening_lesson = lessons_by_course_number[(course_slug, int(listening_number))]
                if listening_key is None:
                    listening_key = editorial_identity.bootstrap_key(
                        "lesson_media", course_slug, listening_number, listening_position
                    )
                media_by_key = {
                    str(media["editorial_key"]): media
                    for media in listening_lesson.get("media", [])
                }
                listening_media = media_by_key.get(
                    editorial_identity.validate_key(listening_key)
                )
                if listening_media is None:
                    raise ValueError(
                        f"Checkpoint {course_slug}/{unit['slug']} referencia mídia inexistente "
                        f"na Aula {listening_number}."
                    )
                if listening_media.get("kind") != "conversation_audio":
                    raise ValueError(
                        f"Checkpoint {course_slug}/{unit['slug']} deve usar áudio de conversa."
                    )

            if unit_lessons and int(review["position"]) <= max(
                int(lesson["position"]) for lesson in unit_lessons
            ):
                raise ValueError(
                    f"Checkpoint {course_slug}/{unit['slug']} deve vir depois das aulas."
                )


def load_seed_graph(path: Path | None = None) -> tuple[int, Graph]:
    """Valida o pacote completo antes de consultar ou escrever no banco."""
    catalog_path = path.with_name("courses.json") if path is not None else None
    courses = load_course_seed(catalog_path)
    lessons = load_seed(path)
    validate_writing_prompts(lessons)
    validate_editorial_provenance(lessons)
    validate_exercises(lessons)
    validate_course_reviews(courses, lessons)
    return len(lessons), seed_graph(courses, lessons)


async def preview_seed(session: AsyncSession, path: Path | None = None) -> dict[str, Any]:
    _, graph = load_seed_graph(path)
    return await preview_graph(session, graph)


async def seed_lessons(session: AsyncSession, path: Path | None = None) -> int:
    """Insere conteúdo novo; reaplicação idêntica não altera IDs nem timestamps.

    Mudanças/omissões de conteúdo existente são bloqueadas integralmente antes
    de DML, inclusive sem referências de alunos, até o versionamento 40B.2.
    """
    total, graph = load_seed_graph(path)
    await apply_graph(session, graph)
    log.info("seed aplicado: %d aulas", total)
    return total
