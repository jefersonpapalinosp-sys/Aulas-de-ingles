"""Sprint 40B.2f: reorder preview is strict, versioned and read-only."""

import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from sqlalchemy import event

from app import cli
from app.db import seed
from app.db.seed_plan import seed_graph
from app.db.session import get_engine
from app.services.editorial_reorder_plan import (
    compare_reorder_graphs,
    preview_editorial_reorder,
)
from tests.test_seed_plan import editorial_rows, sequences


def package():
    return deepcopy(seed.load_course_seed()), deepcopy(seed.load_seed())


def exercise_reorder():
    courses, lessons = package()
    stored = seed_graph(courses, lessons)
    lesson = lessons[0]
    first, second = lesson["exercises"][:2]
    first["position"], second["position"] = second["position"], first["position"]
    lesson.update(
        content_version=2,
        editorial_status="reviewed",
        review_note="Reordenação editorial revisada sem mudança semântica.",
        reviewed_at=datetime.now(UTC).isoformat(),
    )
    return stored, seed_graph(courses, lessons)


def test_lesson_reorder_requires_stable_identity_and_new_reviewed_version():
    stored, wanted = exercise_reorder()
    report = compare_reorder_graphs(wanted, stored)
    assert report["allowed"]
    assert report["counts"] == {
        "reordered_entities": 2,
        "lesson_version_bumps": 1,
        "checkpoint_version_bumps": 0,
        "blockers": 0,
    }
    assert {change["editorial_key"] for change in report["reordered_entities"]} == {
        key[0]
        for key, value in wanted["exercise"].items()
        if value["lesson_id"] == (("voa-level-1",), 1) and value["position"] in {0, 1}
    }
    assert not report["apply_available"] and report["dry_run"]


def test_reorder_without_version_bump_is_blocked():
    courses, lessons = package()
    stored = seed_graph(courses, lessons)
    first, second = lessons[0]["exercises"][:2]
    first["position"], second["position"] = second["position"], first["position"]
    report = compare_reorder_graphs(seed_graph(courses, lessons), stored)
    assert not report["allowed"]
    assert "lesson_version_bump_required" in {blocker["code"] for blocker in report["blockers"]}


@pytest.mark.parametrize("mutation", ["semantic", "parent", "unsupported", "mixed"])
def test_reorder_preview_rejects_mixed_or_unsupported_changes(mutation):
    stored, wanted = exercise_reorder()
    if mutation == "semantic":
        next(iter(wanted["exercise"].values()))["prompt"] += " changed"
    elif mutation == "parent":
        next(iter(wanted["exercise"].values()))["lesson_id"] = (("voa-level-1",), 2)
    elif mutation == "unsupported":
        row = next(iter(wanted["phrase"].values()))
        row["position"] += 100
    else:
        wanted["writing_prompt"].pop(next(iter(wanted["writing_prompt"])))
    report = compare_reorder_graphs(wanted, stored)
    assert not report["allowed"]
    codes = {blocker["code"] for blocker in report["blockers"]}
    assert codes & {
        "semantic_change",
        "parent_changed",
        "unsupported_or_semantic_change",
        "mixed_create_or_omission",
    }


def test_checkpoint_question_reorder_requires_single_content_version_increment():
    courses, lessons = package()
    stored = seed_graph(courses, lessons)
    review = next(
        unit["review"] for course in courses for unit in course["units"] if unit.get("review")
    )
    first, second = review["questions"][:2]
    first["position"], second["position"] = second["position"], first["position"]
    review["content_version"] += 1
    report = compare_reorder_graphs(seed_graph(courses, lessons), stored)
    assert report["allowed"]
    assert report["counts"]["reordered_entities"] == 2
    assert report["counts"]["checkpoint_version_bumps"] == 1

    review["content_version"] += 1
    report = compare_reorder_graphs(seed_graph(courses, lessons), stored)
    assert not report["allowed"]
    assert "checkpoint_version_must_increment_once" in {
        blocker["code"] for blocker in report["blockers"]
    }


def test_identical_catalog_is_not_mistaken_for_a_reorder():
    courses, lessons = package()
    graph = seed_graph(courses, lessons)
    report = compare_reorder_graphs(graph, graph)
    assert not report["allowed"]
    assert report["blockers"] == [
        {"code": "no_reorder_requested", "table": "catalog", "key": (), "fields": []}
    ]


async def test_database_preview_is_consistent_read_only_and_exposes_no_personal_values(session):
    _, wanted = exercise_reorder()
    before = await editorial_rows(session)
    counters = await sequences(session)
    await session.rollback()
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", observe)
    try:
        report = await preview_editorial_reorder(session, wanted)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert report["allowed"] and report["identity_storage"] == "persisted"
    assert report["personal_values_exposed"] is False
    assert isinstance(report["personal_direct_references_preserved"], dict)
    assert all(sql.lstrip().split()[0] in {"SELECT", "SET"} for sql in statements)
    assert any("REPEATABLE READ, READ ONLY" in sql for sql in statements)
    assert await editorial_rows(session) == before
    assert await sequences(session) == counters
    serialized = json.dumps(report, default=str)
    assert "password_hash" not in serialized and "answer" not in serialized


async def test_database_preview_rejects_dirty_session(session):
    _, wanted = exercise_reorder()
    await session.connection()
    with pytest.raises(ValueError, match="sessão nova"):
        await preview_editorial_reorder(session, wanted)


@pytest.mark.parametrize("flag", ["--apply", "--force", "--delete"])
def test_reorder_cli_has_no_mutation_flag(monkeypatch, flag):
    async def forbidden(*args):
        pytest.fail("unknown flag must fail before loading seed or opening database")

    monkeypatch.setattr(cli, "_editorial_reorder_plan", forbidden)
    with pytest.raises(SystemExit) as error:
        cli.main_com_argumentos(["editorial-reorder-plan", flag])
    assert error.value.code == 2
