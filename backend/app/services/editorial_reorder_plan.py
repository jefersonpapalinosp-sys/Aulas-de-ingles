"""Read-only contract for controlled editorial reordering (Sprint 40B.2f).

This module deliberately has no apply path.  It proves that a proposed seed
changes display order only, that stable identities and parents are preserved,
and that the owning lesson/checkpoint receives the required version bump.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from collections import defaultdict
from typing import Any, cast

from sqlalchemy import Table, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import editorial_identity as identities
from app.db.base import Base
from app.db.seed_plan import BY_NAME, SPECS, Graph, Key, read_graph

PREVIEW_TIMEOUT_SECONDS = 30
REPORT_LIMIT = 500

# Only entities whose identity no longer depends on position may be reordered.
LESSON_ORDERED = {
    "exercise": "lesson_id",
    "lesson_media": "lesson_id",
    "vocab_item": "lesson_id",
    "writing_prompt": "lesson_id",
}
REVIEW_ORDERED = {"course_review_question": "review_id"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def catalog_sha256(graph: Graph) -> str:
    return _hash({name: sorted(rows.values(), key=_json) for name, rows in graph.items()})


def _project_catalog(wanted: Graph, stored: Graph) -> Graph:
    """Project updates/additive versions while retaining all historical rows."""
    projected = copy.deepcopy(stored)
    for name, rows in wanted.items():
        for key, values in rows.items():
            if key in projected[name] or name == "lesson_version":
                projected[name][key] = copy.deepcopy(values)
    return projected


def _fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(
        field for field in before.keys() | after.keys() if before.get(field) != after.get(field)
    )


def _lesson_parent(table: str, values: dict[str, Any], graph: Graph) -> Key | None:
    if table in LESSON_ORDERED:
        return cast(Key, values[LESSON_ORDERED[table]])
    if table == "transcript_cue":
        media = graph["lesson_media"].get(values["media_id"])
        return media["lesson_id"] if media is not None else None
    return None


def _order_parent(table: str, values: dict[str, Any]) -> Key:
    if table == "transcript_cue":
        return cast(Key, values["media_id"])
    if table in LESSON_ORDERED:
        return cast(Key, values[LESSON_ORDERED[table]])
    return cast(Key, values[REVIEW_ORDERED[table]])


def _group_rows(table: str, parent: Key, graph: Graph) -> dict[Key, dict[str, Any]]:
    rows: dict[Key, dict[str, Any]] = {}
    for key, values in graph[table].items():
        if _order_parent(table, values) == parent:
            rows[key] = values
    return rows


def compare_reorder_graphs(wanted: Graph, stored: Graph) -> dict[str, Any]:
    """Classify a proposal without reading personal rows or mutating state."""
    blockers: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    groups: dict[tuple[str, Key], list[Key]] = defaultdict(list)
    affected_lessons: set[Key] = set()
    affected_reviews: set[Key] = set()
    review_transitions: dict[Key, tuple[int, int]] = {}
    reordered_count = 0

    def block(code: str, table: str, key: Key, fields: list[str] | None = None) -> None:
        if len(blockers) < REPORT_LIMIT:
            blockers.append({"code": code, "table": table, "key": key, "fields": fields or []})

    for spec in SPECS:
        if spec.name == "lesson_version":
            continue
        before_rows, after_rows = stored[spec.name], wanted[spec.name]
        for key in sorted(before_rows.keys() | after_rows.keys(), key=_json):
            before, after = before_rows.get(key), after_rows.get(key)
            if before == after:
                continue
            if before is None or after is None:
                block(
                    "mixed_create_or_omission",
                    spec.name,
                    key,
                    ["created"] if before is None else ["omitted"],
                )
                continue
            fields = _fields(before, after)
            if spec.name == "course_review" and fields == ["content_version"]:
                old_version = int(before["content_version"])
                new_version = int(after["content_version"])
                review_transitions[key] = (old_version, new_version)
                continue
            if spec.name in LESSON_ORDERED or spec.name == "transcript_cue":
                old_parent = _lesson_parent(spec.name, before, stored)
                new_parent = _lesson_parent(spec.name, after, wanted)
                if old_parent is None or new_parent is None or old_parent != new_parent:
                    block("parent_changed", spec.name, key, fields)
                elif fields != ["position"]:
                    block("semantic_change", spec.name, key, fields)
                else:
                    reordered_count += 1
                    groups[(spec.name, _order_parent(spec.name, before))].append(key)
                    affected_lessons.add(old_parent)
                    if len(changes) < REPORT_LIMIT:
                        changes.append(
                            {
                                "table": spec.name,
                                "editorial_key": key[0],
                                "parent": old_parent,
                                "before_position": before["position"],
                                "after_position": after["position"],
                            }
                        )
                continue
            if spec.name in REVIEW_ORDERED:
                parent_field = REVIEW_ORDERED[spec.name]
                old_parent, new_parent = before[parent_field], after[parent_field]
                if old_parent != new_parent:
                    block("parent_changed", spec.name, key, fields)
                elif fields != ["position"]:
                    block("semantic_change", spec.name, key, fields)
                else:
                    reordered_count += 1
                    groups[(spec.name, old_parent)].append(key)
                    affected_reviews.add(old_parent)
                    if len(changes) < REPORT_LIMIT:
                        changes.append(
                            {
                                "table": spec.name,
                                "editorial_key": key[0],
                                "parent": old_parent,
                                "before_position": before["position"],
                                "after_position": after["position"],
                            }
                        )
                continue
            # Positional tables without immutable UUIDs remain intentionally blocked.
            block("unsupported_or_semantic_change", spec.name, key, fields)

    for (table, parent), changed_keys in groups.items():
        before_group = _group_rows(table, parent, stored)
        after_group = _group_rows(table, parent, wanted)
        before_positions = [row["position"] for row in before_group.values()]
        after_positions = [row["position"] for row in after_group.values()]
        if (
            before_group.keys() != after_group.keys()
            or len(changed_keys) < 2
            or len(before_positions) != len(set(before_positions))
            or len(after_positions) != len(set(after_positions))
            or sorted(before_positions) != sorted(after_positions)
        ):
            block("not_a_position_permutation", table, parent)

    lesson_transitions: list[dict[str, Any]] = []
    all_lessons = {
        row["lesson_id"] for graph in (stored, wanted) for row in graph["lesson_version"].values()
    }
    for lesson in sorted(all_lessons, key=_json):
        before_versions: dict[int, dict[str, Any]] = {
            int(row["version"]): row
            for row in stored["lesson_version"].values()
            if row["lesson_id"] == lesson
        }
        after_versions: dict[int, dict[str, Any]] = {
            int(row["version"]): row
            for row in wanted["lesson_version"].values()
            if row["lesson_id"] == lesson
        }
        if not before_versions or not after_versions:
            block("lesson_version_missing", "lesson_version", lesson)
            continue
        old_version, new_version = max(before_versions), max(after_versions)
        if lesson in affected_lessons:
            candidate = after_versions[new_version]
            if (
                new_version != old_version + 1
                or new_version in before_versions
                or candidate["status"] not in {"reviewed", "published"}
                or candidate["reviewed_at"] is None
            ):
                block("lesson_version_bump_required", "lesson_version", lesson)
            else:
                lesson_transitions.append(
                    {
                        "lesson": lesson,
                        "from_version": old_version,
                        "to_version": new_version,
                        "status": candidate["status"],
                    }
                )
        elif (
            new_version != old_version
            or after_versions[new_version] != before_versions[old_version]
        ):
            block("version_without_reorder", "lesson_version", lesson)

    for review in affected_reviews:
        transition = review_transitions.get(review)
        if transition is None or transition[1] != transition[0] + 1:
            block("checkpoint_version_bump_required", "course_review", review)
    for review, transition in review_transitions.items():
        if review not in affected_reviews:
            block(
                "checkpoint_version_without_reorder",
                "course_review",
                review,
                ["content_version"],
            )
        elif transition[1] != transition[0] + 1:
            block(
                "checkpoint_version_must_increment_once",
                "course_review",
                review,
                ["content_version"],
            )

    if reordered_count > REPORT_LIMIT:
        block("reorder_limit_exceeded", "catalog", (), [str(REPORT_LIMIT)])
    if not reordered_count:
        block("no_reorder_requested", "catalog", ())

    changes = sorted(changes, key=lambda item: _json((item["table"], item["editorial_key"])))
    contract = {
        "policy": "reorder_preview_only_40B2f",
        "identity_contract": "explicit_uuid_v1",
        "reordered_entities": changes,
        "lesson_version_transitions": lesson_transitions,
        "checkpoint_version_transitions": [
            {"review": key, "from_version": value[0], "to_version": value[1]}
            for key, value in sorted(review_transitions.items(), key=lambda item: _json(item[0]))
        ],
        "blockers": blockers,
        "catalog_before_sha256": catalog_sha256(stored),
        "catalog_candidate_sha256": catalog_sha256(wanted),
        "catalog_after_sha256": catalog_sha256(_project_catalog(wanted, stored)),
    }
    return {
        "schema_version": "1.2",
        **contract,
        "allowed": not blockers,
        "dry_run": True,
        "apply_available": False,
        "counts": {
            "reordered_entities": reordered_count,
            "lesson_version_bumps": len(lesson_transitions),
            "checkpoint_version_bumps": len(review_transitions),
            "blockers": len(blockers),
        },
        "reordered_entities_truncated": reordered_count > REPORT_LIMIT,
        "plan_sha256": _hash(contract),
        "notice": "Prévia somente leitura. Ela não reserva o banco e não oferece --apply. "
        "Uma futura aplicação deverá reler e bloquear o catálogo sob transação exclusiva.",
    }


def _direct_reference_edges(target: Table) -> list[tuple[Table, Any]]:
    editorial_tables = {spec.name for spec in SPECS}
    edges: list[tuple[Table, Any]] = []
    seen: set[tuple[str, str]] = set()
    for table in Base.metadata.tables.values():
        if table.name in editorial_tables:
            continue
        for foreign_key in table.foreign_keys:
            if foreign_key.column.table is not target or foreign_key.column.name != "id":
                continue
            edge = (table.name, foreign_key.parent.name)
            if edge not in seen:
                edges.append((table, foreign_key.parent))
                seen.add(edge)
    return edges


async def collect_personal_reference_impact(
    session: AsyncSession,
    report: dict[str, Any],
    ids: dict[str, dict[Key, int]],
) -> dict[str, int]:
    affected: dict[str, set[int]] = defaultdict(set)
    for change in report["reordered_entities"]:
        table = change["table"]
        key = (change["editorial_key"],)
        if key in ids[table]:
            affected[table].add(ids[table][key])
    for transition in report["checkpoint_version_transitions"]:
        review = tuple(transition["review"])
        if review in ids["course_review"]:
            affected["course_review"].add(ids["course_review"][review])

    impact: dict[str, int] = {}
    for target_name, target_ids in sorted(affected.items()):
        if not target_ids:
            continue
        target = BY_NAME[target_name].table
        for table, column in _direct_reference_edges(target):
            label = f"{table.name}.{column.name}->{target_name}.id"
            impact[label] = int(
                await session.scalar(
                    select(func.count()).select_from(table).where(column.in_(target_ids))
                )
                or 0
            )
    return impact


async def preview_editorial_reorder(session: AsyncSession, wanted: Graph) -> dict[str, Any]:
    """Return a consistent, bounded and write-free reorder assessment."""
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ValueError("A prévia de reordenação exige sessão nova sem alterações pendentes.")
    async with asyncio.timeout(PREVIEW_TIMEOUT_SECONDS), session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        await session.execute(text("SET LOCAL statement_timeout = '20s'"))
        stored, ids = await read_graph(session)
        report = compare_reorder_graphs(wanted, stored)
        report["snapshot_at"] = str(await session.scalar(select(func.transaction_timestamp())))
        report["identity_storage"] = (
            "persisted" if await identities.schema_available(session) else "legacy_projection"
        )
        if report["identity_storage"] != "persisted":
            report["allowed"] = False
            report["blockers"].append(
                {
                    "code": "stable_identity_migration_required",
                    "table": "catalog",
                    "key": (),
                    "fields": [],
                }
            )
            report["counts"]["blockers"] += 1
        report["personal_direct_references_preserved"] = await collect_personal_reference_impact(
            session, report, ids
        )
        report["personal_values_exposed"] = False
        return report
