"""Read-only editorial diff and insert-only seed (Sprint 40B.1).

Until immutable snapshots/archive rules exist, *all* changes to existing
content are refused, even without student references. No personal tables are
read and no cascade/update/delete is used. Six referenced entity types use
explicit immutable UUIDs. Cross-entity listening links resolve to those
identities, not to mutable display positions. Positions remain ordering fields;
moving or editing existing content is still blocked.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Table, UniqueConstraint, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import editorial_identity as identities
from app.db import models
from app.domain.writing_rubric import WritingRequirement
from app.services.publication import PUBLICATION_LOCK

Key = tuple[Any, ...]
Graph = dict[str, dict[Key, dict[str, Any]]]
MAX_ROWS_PER_TABLE = 100_000
REPORT_LIMIT = 500


@dataclass(frozen=True)
class Spec:
    name: str
    key: tuple[str, ...]
    refs: tuple[tuple[str, str], ...] = ()

    @property
    def table(self) -> Table:
        return models.Course.metadata.tables[self.name]

    @property
    def fields(self) -> list[str]:
        return [
            c.name for c in self.table.columns if c.name not in {"id", "created_at", "updated_at"}
        ]


# Topological order; explicit editorial allowlist, never user data.
SPECS = (
    Spec("course", ("slug",)),
    Spec("course_unit", ("course_id", "slug"), (("course_id", "course"),)),
    Spec("lesson", ("course_id", "number"), (("course_id", "course"), ("unit_id", "course_unit"))),
    Spec("content_source", ("lesson_id", "kind"), (("lesson_id", "lesson"),)),
    Spec("lesson_version", ("lesson_id", "version"), (("lesson_id", "lesson"),)),
    Spec("lesson_goal", ("lesson_id", "position"), (("lesson_id", "lesson"),)),
    Spec("grammar_block", ("lesson_id", "position"), (("lesson_id", "lesson"),)),
    Spec("grammar_row", ("block_id", "position"), (("block_id", "grammar_block"),)),
    Spec("phrase", ("lesson_id", "position"), (("lesson_id", "lesson"),)),
    Spec("pronunciation_note", ("lesson_id", "position"), (("lesson_id", "lesson"),)),
    Spec("vocab_item", ("editorial_key",), (("lesson_id", "lesson"),)),
    Spec("exercise", ("editorial_key",), (("lesson_id", "lesson"),)),
    Spec("exercise_answer", ("exercise_id", "position"), (("exercise_id", "exercise"),)),
    Spec("exercise_hint", ("exercise_id", "level"), (("exercise_id", "exercise"),)),
    Spec(
        "lesson_media",
        ("editorial_key",),
        (("lesson_id", "lesson"), ("listening_exercise_id", "exercise")),
    ),
    Spec("transcript_cue", ("editorial_key",), (("media_id", "lesson_media"),)),
    Spec("writing_prompt", ("editorial_key",), (("lesson_id", "lesson"),)),
    Spec(
        "course_review",
        ("unit_id",),
        (
            ("unit_id", "course_unit"),
            ("listening_course_id", "course"),
            ("listening_lesson_id", "lesson"),
            ("listening_media_id", "lesson_media"),
        ),
    ),
    Spec("course_review_question", ("editorial_key",), (("review_id", "course_review"),)),
)
BY_NAME = {spec.name: spec for spec in SPECS}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _optional_timestamp(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} precisa ser um timestamp RFC 3339 ou null.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} precisa informar fuso horário.")
    return parsed.astimezone(UTC)


def seed_graph(courses: list[dict[str, Any]], lessons: list[dict[str, Any]]) -> Graph:
    """Normalize exactly the persisted fields, before any connection/write."""
    graph: Graph = {spec.name: {} for spec in SPECS}

    def add(name: str, raw: dict[str, Any], **overrides: Any) -> Key:
        spec = BY_NAME[name]
        source = raw | overrides
        values = {}
        for field in spec.fields:
            if field not in source and not spec.table.c[field].nullable:
                raise ValueError(f"Campo obrigatório ausente: {name}.{field}.")
            values[field] = source.get(field)
        if name in identities.TABLES:
            values["editorial_key"] = identities.validate_key(source.get("editorial_key"))
        key = tuple(values[field] for field in spec.key)
        if key in graph[name]:
            raise ValueError(f"Identidade editorial duplicada: {name} {_json(key)}.")
        graph[name][key] = values
        return key

    def stable_ref(
        raw: dict[str, Any],
        explicit_field: str,
        table: str,
        *legacy_coordinate: Any,
    ) -> Key | None:
        """Normalize an explicit UUID or the frozen UUIDv5 of the baseline.

        The compatibility coordinate is converted to identity before graph
        comparison. It is never looked up as the entity's current position.
        """
        value = raw.get(explicit_field)
        if value is None:
            if not legacy_coordinate or legacy_coordinate[-1] is None:
                return None
            value = identities.bootstrap_key(table, *legacy_coordinate)
        return (identities.validate_key(value),)

    pending_reviews: list[tuple[dict[str, Any], Key, str]] = []
    for course in courses:
        course_key = add("course", course)
        for unit in course["units"]:
            unit_key = add("course_unit", unit, course_id=course_key)
            if review := unit.get("review"):
                pending_reviews.append((review, unit_key, str(course["slug"])))

    for raw in lessons:
        course_key = (raw["course_slug"],)
        unit_key = (course_key, raw["unit_slug"])
        lesson_key = add("lesson", raw, course_id=course_key, unit_id=unit_key)
        accessed = date.fromisoformat(raw["source_accessed_at"])
        for kind, title, publisher, url, license_note in (
            (
                "official",
                f"VOA Let's Learn English — Lesson {raw['number']}",
                "VOA Learning English",
                raw["voa_url"],
                "Texto e MP3 da VOA Learning English em domínio público, com crédito à fonte; "
                "materiais identificados como provenientes de agências terceiras não se incluem.",
            ),
            (
                "authorial",
                "Explicações e atividades do Aulas de Inglês",
                "Aulas de Inglês",
                None,
                "Conteúdo autoral do projeto; não substitui a fonte oficial.",
            ),
        ):
            add(
                "content_source",
                {},
                lesson_id=lesson_key,
                kind=kind,
                title=title,
                publisher=publisher,
                url=url,
                license_note=license_note,
                accessed_at=accessed,
            )
        # Ausência de timestamp continua ausência: acesso à fonte, execução do
        # seed e revisão pedagógica são eventos diferentes.
        status = raw["editorial_status"]
        add(
            "lesson_version",
            {},
            lesson_id=lesson_key,
            version=int(raw.get("content_version", 1)),
            status=status,
            learning_strategy=raw["learning_strategy"],
            review_note=raw["review_note"],
            reviewed_at=_optional_timestamp(raw.get("reviewed_at"), "reviewed_at"),
            published_at=_optional_timestamp(raw.get("published_at"), "published_at"),
        )
        for position, goal in enumerate(raw["goals"]):
            add("lesson_goal", {}, lesson_id=lesson_key, position=position, text=goal)
        for block in raw["grammar_blocks"]:
            block_key = add("grammar_block", block, lesson_id=lesson_key)
            for row in block["rows"]:
                add("grammar_row", row, block_id=block_key)
        for name, field in (
            ("phrase", "phrases"),
            ("pronunciation_note", "pronunciation"),
            ("vocab_item", "vocab"),
        ):
            for item in raw[field]:
                add(name, item, lesson_id=lesson_key)
        for exercise in raw["exercises"]:
            activity = exercise.get("activity_type", "gap_fill")
            skill = exercise.get("skill", "grammar")
            objective = (
                "listen"
                if skill == "listening"
                else "correct"
                if activity == "transformation"
                else "recognize"
                if activity in {"multiple_choice", "classification"}
                else "apply"
            )
            exercise_key = add(
                "exercise",
                exercise,
                lesson_id=lesson_key,
                activity_type=activity,
                skill=skill,
                objective=exercise.get("objective", objective),
            )
            for position, answer in enumerate(exercise["answers"]):
                add(
                    "exercise_answer", {}, exercise_id=exercise_key, position=position, value=answer
                )
            for level, content in enumerate(exercise.get("hints", []), start=1):
                add("exercise_hint", {}, exercise_id=exercise_key, level=level, content=content)
        for media in raw.get("media", []):
            exercise_ref = stable_ref(
                media,
                "listening_exercise_key",
                "exercise",
                raw["course_slug"],
                raw["number"],
                media.get("listening_exercise_position"),
            )
            media_key = add(
                "lesson_media",
                media,
                lesson_id=lesson_key,
                listening_exercise_id=exercise_ref,
                license_reviewed_at=date.fromisoformat(media["license_reviewed_at"]),
                transcript=media.get("transcript", []),
            )
            for cue in media.get("cues", []):
                add(
                    "transcript_cue",
                    cue,
                    media_id=media_key,
                    start_seconds=float(cue["start_seconds"]),
                    end_seconds=float(cue["end_seconds"]),
                )
        for prompt in raw.get("writing_prompts", []):
            add(
                "writing_prompt",
                prompt,
                lesson_id=lesson_key,
                requirements=[
                    WritingRequirement.model_validate(rule).model_dump()
                    for rule in prompt["requirements"]
                ],
            )

    for review, unit_key, course_slug in pending_reviews:
        listening_number = review.get("listening_lesson_number")
        lesson_ref = (
            ((course_slug,), int(listening_number)) if listening_number is not None else None
        )
        media_ref = stable_ref(
            review,
            "listening_media_key",
            "lesson_media",
            course_slug,
            listening_number,
            review.get("listening_media_position"),
        )
        review_key = add(
            "course_review",
            review,
            unit_id=unit_key,
            listening_course_id=(course_slug,) if listening_number is not None else None,
            listening_lesson_id=lesson_ref,
            listening_media_id=media_ref,
        )
        for question in review["questions"]:
            add("course_review_question", question, review_id=review_key)

    for spec in SPECS:
        for values in graph[spec.name].values():
            for field, parent in spec.refs:
                if values[field] is not None and values[field] not in graph[parent]:
                    raise ValueError(f"Referência editorial ausente: {spec.name}.{field}.")
            if spec.name == "lesson_media" and values["listening_exercise_id"] is not None:
                exercise = graph["exercise"][values["listening_exercise_id"]]
                if exercise["lesson_id"] != values["lesson_id"]:
                    raise ValueError("Mídia não pode referenciar exercício de outra aula.")
            if spec.name == "course_review" and values["listening_media_id"] is not None:
                lesson = graph["lesson"][values["listening_lesson_id"]]
                media = graph["lesson_media"][values["listening_media_id"]]
                if (
                    values["unit_id"][0] != values["listening_course_id"]
                    or lesson["course_id"] != values["listening_course_id"]
                    or media["lesson_id"] != values["listening_lesson_id"]
                ):
                    raise ValueError("Checkpoint não pode referenciar mídia de outro curso/aula.")
        # Validate alternate unique keys too (slugs, positions, etc.).
        for constraint in spec.table.constraints:
            if isinstance(constraint, UniqueConstraint) and "id" not in constraint.columns:
                seen = set()
                for values in graph[spec.name].values():
                    value = tuple(values[column.name] for column in constraint.columns)
                    if value in seen:
                        raise ValueError(f"Chave editorial duplicada: {spec.name}.")
                    seen.add(value)
    return graph


async def read_graph(session: AsyncSession) -> tuple[Graph, dict[str, dict[Key, int]]]:
    graph: Graph = {spec.name: {} for spec in SPECS}
    ids: dict[str, dict[Key, int]] = {spec.name: {} for spec in SPECS}
    keys: dict[str, dict[int, Key]] = {spec.name: {} for spec in SPECS}
    persisted_keys = await identities.schema_available(session)
    for spec in SPECS:
        columns = [c for c in spec.table.c if persisted_keys or c.name != "editorial_key"]
        rows = (await session.execute(select(*columns).limit(MAX_ROWS_PER_TABLE + 1))).mappings()
        for index, row in enumerate(rows):
            if index >= MAX_ROWS_PER_TABLE:
                raise ValueError("Catálogo excede o limite de prévia; requer operação dedicada.")
            values = {field: row[field] for field in spec.fields if field in row}
            for field, parent in spec.refs:
                if values[field] is not None:
                    values[field] = keys[parent][values[field]]
            if not persisted_keys and spec.name in identities.TABLES:
                values["editorial_key"] = identities.projected_legacy_key(spec.name, values, graph)
            key = tuple(values[field] for field in spec.key)
            graph[spec.name][key] = values
            ids[spec.name][key] = row["id"]
            keys[spec.name][row["id"]] = key
    return graph, ids


def _extends_existing(name: str, values: dict[str, Any], wanted: Graph, stored: Graph) -> bool:
    """New child rows may change an existing lesson/checkpoint's interpretation."""
    for field, parent in BY_NAME[name].refs:
        key = values[field]
        if key is None:
            continue
        if parent in {"lesson", "course_review"} and key in stored[parent]:
            return True
        if _extends_existing(parent, wanted[parent][key], wanted, stored):
            return True
    return False


def compare_graphs(wanted: Graph, stored: Graph) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    counts = {"create": 0, "change": 0, "omitted": 0, "retained": 0, "unchanged": 0, "blocked": 0}
    current_versions: dict[Key, int] = {}
    for version in wanted["lesson_version"].values():
        lesson_key = version["lesson_id"]
        current_versions[lesson_key] = max(current_versions.get(lesson_key, 0), version["version"])
    for spec in SPECS:
        before, after = stored[spec.name], wanted[spec.name]
        for key in sorted(before.keys() | after.keys(), key=_json):
            old, new = before.get(key), after.get(key)
            if old == new:
                counts["unchanged"] += 1
                continue
            operation = "create" if old is None else "omitted" if new is None else "change"
            blocked = old is not None or _extends_existing(spec.name, new or {}, wanted, stored)
            # Older version metadata was already append-only in the legacy seed.
            # Preserve it verbatim; absence does not mean a requested removal.
            # A downgrade still blocks because the omitted higher version fails this condition.
            if (
                spec.name == "lesson_version"
                and old is not None
                and new is None
                and old["version"] < current_versions.get(old["lesson_id"], 0)
            ):
                operation, blocked, new = "retained", False, old
            counts[operation] += 1
            counts["blocked"] += int(blocked)
            if len(changes) < REPORT_LIMIT:
                changes.append(
                    {
                        "table": spec.name,
                        "key": key,
                        "operation": operation,
                        "blocked": blocked,
                        "reason": (
                            "historical_metadata_preserved"
                            if operation == "retained"
                            else "existing_content_requires_versioning"
                            if old is not None
                            else "existing_parent_requires_versioning"
                            if blocked
                            else "new_content"
                        ),
                        "fields": sorted(
                            field
                            for field in (old or {}).keys() | (new or {}).keys()
                            if (old or {}).get(field) != (new or {}).get(field)
                        ),
                        "before_sha256": _hash(old) if old is not None else None,
                        "after_sha256": _hash(new) if new is not None else None,
                    }
                )
    return {
        "schema_version": "1.1",
        "identity_contract": "explicit_uuid_v1",
        "policy": "insert_only_40B1",
        "allowed": counts["blocked"] == 0,
        "counts": counts,
        "changes": changes,
        "changes_truncated": sum(counts[k] for k in ("create", "change", "omitted", "retained"))
        > REPORT_LIMIT,
        "seed_sha256": _hash(
            {name: sorted(rows.values(), key=_json) for name, rows in wanted.items()}
        ),
        "notice": "Omissões não autorizam exclusão. Alterar conteúdo existente ou seus filhos "
        "exige versionamento/arquivamento (40B.2); não existe --force. "
        "Prévia não reserva o banco: a aplicação sempre verifica novamente.",
    }


class SeedBlocked(ValueError):
    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        super().__init__("Seed bloqueado: conteúdo existente deve ser preservado (40B.2).")


async def preview_graph(session: AsyncSession, wanted: Graph) -> dict[str, Any]:
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ValueError("A prévia exige uma sessão nova, sem transação ou alterações pendentes.")
    async with session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        await session.execute(text("SET LOCAL statement_timeout = '20s'"))
        stored, _ = await read_graph(session)
        report = compare_graphs(wanted, stored)
        report["snapshot_at"] = str(await session.scalar(select(func.transaction_timestamp())))
        report["dry_run"] = True
        persisted_keys = await identities.schema_available(session)
        report["identity_storage"] = "persisted" if persisted_keys else "legacy_projection"
        if not persisted_keys:
            report["allowed"] = False
            report["schema_blocker"] = "Migration c51f9de246a8 obrigatória antes de aplicar seed."
        # Explicit status requests get aggregate impact in the SAME read-only
        # snapshot, not an automatic mutation or an omission-to-delete heuristic.
        candidates = [
            row
            for key, row in wanted["course_unit"].items()
            if row["status"] == "archived"
            and key in stored["course_unit"]
            and stored["course_unit"][key]["status"] == "published"
        ]
        report["archive_requests"] = []
        report["archive_requests_truncated"] = len(candidates) > 5
        if candidates:
            from app.services.editorial_plan import collect_unit_archive

            for row in candidates[:5]:
                plan = await collect_unit_archive(session, row["course_id"][0], row["slug"])
                report["archive_requests"].append(
                    {
                        name: plan[name]
                        for name in (
                            "target",
                            "catalog_sha256",
                            "personal_rows_preserved",
                            "external_checkpoint_dependencies",
                            "active_practice_sessions",
                            "blockers",
                        )
                    }
                )
        report["archive_apply_via_seed"] = False
    return report


async def apply_graph(session: AsyncSession, wanted: Graph) -> None:
    if session.new or session.dirty or session.deleted:
        raise ValueError("Seed exige sessão sem alterações ORM pendentes.")
    try:
        # Callers may have done reads, but an older repeatable-read snapshot
        # cannot be used to authorize a later import after acquiring the lock.
        if await session.scalar(text("SHOW transaction_isolation")) != "read committed":
            raise ValueError("Aplicação do seed exige isolamento READ COMMITTED.")
        await session.execute(text("SET LOCAL statement_timeout = '20s'"))
        if not await identities.schema_available(session):
            raise ValueError(
                "Migration c51f9de246a8 obrigatória; nenhuma escrita de seed permitida."
            )
        if not await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:namespace, :key)"),
            {"namespace": PUBLICATION_LOCK[0], "key": PUBLICATION_LOCK[1]},
        ):
            raise ValueError("Catálogo ocupado; nenhuma escrita de seed permitida.")
        # NOWAIT avoids a stalled deployment. Only editorial tables are locked;
        # personal references can be inserted because existing content is immutable.
        names = ", ".join(f'"{spec.name}"' for spec in sorted(SPECS, key=lambda s: s.name))
        await session.execute(text(f"LOCK TABLE {names} IN SHARE ROW EXCLUSIVE MODE NOWAIT"))
        stored, ids = await read_graph(session)
        report = compare_graphs(wanted, stored)
        report.update(dry_run=False, applied=False)
        if not report["allowed"]:
            raise SeedBlocked(report)
        for spec in SPECS:
            for key, source in wanted[spec.name].items():
                if key in ids[spec.name]:
                    continue
                values = dict(source)
                for field, parent in spec.refs:
                    if values[field] is not None:
                        values[field] = ids[parent][values[field]]
                row_id = await session.scalar(
                    insert(spec.table).values(**values).returning(spec.table.c.id)
                )
                assert row_id is not None
                ids[spec.name][key] = row_id
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
