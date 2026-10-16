"""Auditoria somente leitura de rubricas e proveniência editorial.

O relatório compara o catálogo persistido com o pacote atual, mas nunca serve
como autorização de escrita. Em particular, diferenças de rubrica são
classificadas pelo efeito no avaliador determinístico atual; resultados
históricos continuam sendo lidos de seus próprios snapshots.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentSource, Course, Lesson, LessonVersion, WritingPrompt
from app.db.seed import load_seed, validate_writing_prompts
from app.domain.writing_rubric import WritingRequirement

REPORT_LIMIT = 500
LEGACY_GENERATED_REVIEWED_AT = datetime(2026, 10, 7, tzinfo=UTC)
PROMPT_FIELDS = ("title", "instructions", "min_words", "min_sentences")
EVALUATION_FIELDS = ("terms", "kind", "match_mode", "count_mode", "min_count")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _canonical(requirements: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        WritingRequirement.model_validate(requirement).model_dump(mode="json")
        for requirement in requirements
    ]


def _evaluation_signature(requirements: list[dict[str, object]]) -> list[str]:
    """Representa apenas o que pode mudar o resultado booleano da rubrica.

    Rótulos e ordem alteram a apresentação/snapshot, mas a prontidão é a
    conjunção de todos os requisitos; portanto eles não mudam o resultado.
    """
    return sorted(
        _json({field: requirement[field] for field in EVALUATION_FIELDS})
        for requirement in _canonical(requirements)
    )


def _changed_evaluation_fields(
    before: list[dict[str, object]], after: list[dict[str, object]]
) -> set[str]:
    old = _canonical(before)
    new = _canonical(after)
    changed: set[str] = set()
    for index in range(max(len(old), len(new))):
        if index >= len(old) or index >= len(new):
            changed.add("requirement_count")
            continue
        changed.update(
            field for field in EVALUATION_FIELDS if old[index][field] != new[index][field]
        )
    return changed


async def collect_editorial_audit(
    session: AsyncSession, lessons: list[dict[str, Any]]
) -> dict[str, Any]:
    """Coleta o relatório dentro da transação somente leitura do chamador."""
    prompt_rows = (
        await session.execute(
            select(
                Course.slug,
                Lesson.number,
                WritingPrompt.position,
                WritingPrompt.title,
                WritingPrompt.instructions,
                WritingPrompt.min_words,
                WritingPrompt.min_sentences,
                WritingPrompt.requirements,
            )
            .join(Lesson, Lesson.course_id == Course.id)
            .join(WritingPrompt, WritingPrompt.lesson_id == Lesson.id)
        )
    ).all()
    stored = {(row[0], row[1], row[2]): row for row in prompt_rows}
    seed_keys: set[tuple[str, int, int]] = set()
    counts: Counter[str] = Counter()
    by_course: Counter[str] = Counter()
    changed_fields: Counter[str] = Counter()
    changes: list[dict[str, Any]] = []

    for lesson in lessons:
        for prompt in lesson.get("writing_prompts", []):
            key = (str(lesson["course_slug"]), int(lesson["number"]), int(prompt["position"]))
            seed_keys.add(key)
            current = stored.get(key)
            detail_fields: list[str] = []
            if current is None:
                classification = "missing_in_database"
                before_requirements: list[dict[str, object]] | None = None
                before_payload = None
            else:
                metadata_changes = [
                    field
                    for offset, field in enumerate(PROMPT_FIELDS, start=3)
                    if current[offset] != prompt[field]
                ]
                before_requirements = current[7]
                before_payload = {
                    field: current[offset]
                    for offset, field in enumerate(PROMPT_FIELDS, start=3)
                } | {"requirements": before_requirements}
                try:
                    before_canonical = _canonical(before_requirements)
                    after_canonical = _canonical(prompt["requirements"])
                except ValueError:
                    classification = "invalid_requirement"
                else:
                    if metadata_changes:
                        classification = "prompt_metadata_change"
                        detail_fields = metadata_changes
                    elif before_requirements == prompt["requirements"]:
                        classification = "exact"
                    elif before_canonical == after_canonical:
                        classification = "representation_only"
                        detail_fields = ["requirements_representation"]
                    elif _evaluation_signature(before_requirements) == _evaluation_signature(
                        prompt["requirements"]
                    ):
                        classification = "display_only"
                        detail_fields = ["requirements_display"]
                    else:
                        classification = "evaluation_change"
                        detail_fields = sorted(
                            _changed_evaluation_fields(
                                before_requirements, prompt["requirements"]
                            )
                        )
                        for field in detail_fields:
                            changed_fields[field] += 1
            counts[classification] += 1
            by_course[f"{key[0]}:{classification}"] += 1
            if classification != "exact" and len(changes) < REPORT_LIMIT:
                after_payload = {field: prompt[field] for field in PROMPT_FIELDS} | {
                    "requirements": prompt["requirements"]
                }
                changes.append(
                    {
                        "course_slug": key[0],
                        "lesson_number": key[1],
                        "prompt_position": key[2],
                        "classification": classification,
                        "fields": detail_fields,
                        "before_sha256": _hash(before_payload) if before_payload else None,
                        "after_sha256": _hash(after_payload),
                    }
                )

    extras = sorted(set(stored) - seed_keys)
    counts["extra_in_database"] = len(extras)
    for course_slug, lesson_number, prompt_position in extras:
        if len(changes) >= REPORT_LIMIT:
            break
        changes.append(
            {
                "course_slug": course_slug,
                "lesson_number": lesson_number,
                "prompt_position": prompt_position,
                "classification": "extra_in_database",
                "fields": [],
                "before_sha256": _hash(
                    {
                        field: stored[(course_slug, lesson_number, prompt_position)][offset]
                        for offset, field in enumerate(PROMPT_FIELDS, start=3)
                    }
                    | {
                        "requirements": stored[
                            (course_slug, lesson_number, prompt_position)
                        ][7]
                    }
                ),
                "after_sha256": None,
            }
        )

    version_rows = (
        await session.execute(
            select(
                Course.slug,
                Lesson.number,
                LessonVersion.version,
                LessonVersion.status,
                LessonVersion.reviewed_at,
                LessonVersion.published_at,
            )
            .join(Lesson, Lesson.course_id == Course.id)
            .join(LessonVersion, LessonVersion.lesson_id == Lesson.id)
        )
    ).all()
    source_rows = (
        await session.execute(
            select(Course.slug, Lesson.number, ContentSource.kind, ContentSource.accessed_at)
            .join(Lesson, Lesson.course_id == Course.id)
            .join(ContentSource, ContentSource.lesson_id == Lesson.id)
        )
    ).all()
    latest_source: dict[tuple[str, int], date] = {}
    source_dates: Counter[str] = Counter()
    for course_slug, lesson_number, kind, source_accessed_at in source_rows:
        source_key = (course_slug, lesson_number)
        latest_source[source_key] = max(
            source_accessed_at, latest_source.get(source_key, source_accessed_at)
        )
        source_dates[f"{source_accessed_at.isoformat()}:{kind}"] += 1

    version_dates: Counter[str] = Counter()
    impossible_order = 0
    legacy_generated = 0
    for course_slug, lesson_number, _version, _status, reviewed_at, published_at in version_rows:
        reviewed_key = reviewed_at.date().isoformat() if reviewed_at else "unknown"
        published_key = published_at.date().isoformat() if published_at else "unpublished"
        version_dates[f"{reviewed_key}:{published_key}"] += 1
        if reviewed_at and reviewed_at == LEGACY_GENERATED_REVIEWED_AT:
            legacy_generated += 1
        latest_access = latest_source.get((course_slug, lesson_number))
        if reviewed_at and latest_access and reviewed_at.date() < latest_access:
            impossible_order += 1

    seed_provenance = {
        "lessons": len(lessons),
        "source_accessed_at_explicit": sum("source_accessed_at" in lesson for lesson in lessons),
        "review_note_explicit": sum(bool(lesson.get("review_note")) for lesson in lessons),
        "reviewed_at_explicit": sum(lesson.get("reviewed_at") is not None for lesson in lessons),
        "published_at_explicit": sum(lesson.get("published_at") is not None for lesson in lessons),
        "undated_reviewed_lessons": sum(
            lesson.get("editorial_status") in {"reviewed", "published"}
            and lesson.get("reviewed_at") is None
            for lesson in lessons
        ),
    }
    writing = {
        "seed_prompts": len(seed_keys),
        "stored_prompts": len(stored),
        "counts": dict(sorted(counts.items())),
        "by_course": dict(sorted(by_course.items())),
        "evaluation_change_fields": dict(sorted(changed_fields.items())),
        "changes": changes,
        "changes_truncated": sum(value for key, value in counts.items() if key != "exact")
        > len(changes),
        "apply_available": False,
    }
    provenance = {
        "seed": seed_provenance,
        "stored_lesson_versions": len(version_rows),
        "legacy_generated_reviewed_at": legacy_generated,
        "review_before_latest_source_access": impossible_order,
        "version_date_distribution": dict(sorted(version_dates.items())),
        "source_date_distribution": dict(sorted(source_dates.items())),
    }
    return {
        "schema_version": "1.0",
        "dry_run": True,
        "writing_rubrics": writing,
        "provenance": provenance,
        "release_ready": not any(
            counts[name]
            for name in (
                "evaluation_change",
                "prompt_metadata_change",
                "invalid_requirement",
                "missing_in_database",
                "extra_in_database",
            )
        )
        and impossible_order == 0
        and legacy_generated == 0
        and seed_provenance["undated_reviewed_lessons"] == 0,
        "notice": (
            "Relatório somente leitura. Diferenças semânticas exigem nova versão e "
            "homologação pedagógica; não atualize rubricas ou histórico automaticamente."
        ),
    }


async def preview_editorial_audit(session: AsyncSession) -> dict[str, Any]:
    """Executa a auditoria num snapshot consistente, sem ler dados pessoais."""
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ValueError(
            "A auditoria exige uma sessão nova, sem transação ou alterações pendentes."
        )
    lessons = load_seed()
    validate_writing_prompts(lessons)
    async with session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        await session.execute(text("SET LOCAL statement_timeout = '20s'"))
        report = await collect_editorial_audit(session, lessons)
        report["database"] = await session.scalar(select(func.current_database()))
        report["snapshot_at"] = str(await session.scalar(select(func.transaction_timestamp())))
        report["report_sha256"] = _hash(
            {"writing_rubrics": report["writing_rubrics"], "provenance": report["provenance"]}
        )
        return report
