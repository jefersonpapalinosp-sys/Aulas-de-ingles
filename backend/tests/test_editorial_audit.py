"""40B.2c: auditoria de rubricas/proveniência sem DML."""

import importlib.util
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event, select, text

from app.db import seed
from app.db.models import WritingPrompt
from app.db.session import get_engine
from app.services.editorial_audit import collect_editorial_audit, preview_editorial_audit


async def test_audit_classifies_format_display_and_evaluation_without_content(session):
    lessons = seed.load_seed()
    prompts = list(
        (
            await session.scalars(select(WritingPrompt).order_by(WritingPrompt.id).limit(3))
        ).all()
    )
    first = deepcopy(prompts[0].requirements)
    first[1].pop("kind")
    first[1].pop("match_mode")
    first[1].pop("count_mode")
    first[1].pop("min_count")
    second = deepcopy(prompts[1].requirements)
    second[0]["label"] += " (apresentação)"
    third = deepcopy(prompts[2].requirements)
    third[0]["min_count"] = int(third[0]["min_count"]) + 1
    prompts[0].requirements = first
    prompts[1].requirements = second
    prompts[2].requirements = third
    await session.flush()

    report = await collect_editorial_audit(session, lessons)
    counts = report["writing_rubrics"]["counts"]
    assert counts == {
        "display_only": 1,
        "evaluation_change": 1,
        "exact": 79,
        "extra_in_database": 0,
        "representation_only": 1,
    }
    assert report["writing_rubrics"]["evaluation_change_fields"] == {"min_count": 1}
    rendered = json.dumps(report, ensure_ascii=False)
    assert prompts[0].requirements[0]["terms"][0] not in rendered
    assert "(apresentação)" not in rendered
    assert not report["release_ready"]
    await session.rollback()


async def test_preview_is_repeatable_read_only_and_has_truthful_provenance(session):
    statements: list[str] = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", observe)
    try:
        report = await preview_editorial_audit(session)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert report["dry_run"] and report["writing_rubrics"]["apply_available"] is False
    assert report["writing_rubrics"]["counts"] == {"exact": 82, "extra_in_database": 0}
    assert report["provenance"]["seed"]["review_note_explicit"] == 82
    assert report["provenance"]["seed"]["reviewed_at_explicit"] == 0
    assert report["provenance"]["seed"]["undated_reviewed_lessons"] == 82
    assert report["provenance"]["legacy_generated_reviewed_at"] == 0
    assert not report["release_ready"]
    assert any("REPEATABLE READ, READ ONLY" in statement for statement in statements)
    assert all(statement.lstrip().split()[0] in {"SELECT", "SET"} for statement in statements)
    assert not any(
        "app_user" in statement or "writing_feedback" in statement for statement in statements
    )


def test_seed_rejects_invented_or_incomplete_provenance():
    lessons = seed.load_seed()
    missing_note = deepcopy(lessons)
    del missing_note[0]["review_note"]
    with pytest.raises(ValueError, match="review_note"):
        seed.validate_editorial_provenance(missing_note)

    impossible_date = deepcopy(lessons)
    impossible_date[0]["reviewed_at"] = "2026-10-01T00:00:00Z"
    with pytest.raises(ValueError, match="antes do acesso"):
        seed.validate_editorial_provenance(impossible_date)


@pytest.mark.timezone
async def test_provenance_migration_nulls_generated_dates_without_inventing_downgrade(session):
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/e73c1a9b40d2_truthful_editorial_provenance.py"
    )
    spec = importlib.util.spec_from_file_location("provenance_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def rehearse(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA provenance_migration_test"))
            connection.execute(text("SET LOCAL search_path TO provenance_migration_test"))
            connection.execute(
                text(
                    """CREATE TABLE lesson_version(
                    id integer PRIMARY KEY,
                    review_note varchar(500) NOT NULL,
                    reviewed_at timestamptz NOT NULL,
                    published_at timestamptz NULL)"""
                )
            )
            connection.execute(
                text(
                    """INSERT INTO lesson_version VALUES
                    (1,'Conteúdo revisado contra o plano oficial e adaptado ao piloto.',
                     '2026-10-07 00:00:00+00','2026-10-07 00:00:00+00'),
                    (2,'Com evidência real','2026-10-14 12:00:00+00',NULL)"""
                )
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                rows = list(
                    connection.execute(
                        text(
                            "SELECT id,review_note,reviewed_at,published_at "
                            "FROM lesson_version ORDER BY id"
                        )
                    ).mappings()
                )
                assert rows[0]["reviewed_at"] is None and rows[0]["published_at"] is None
                assert "validação pedagógica humana" in rows[0]["review_note"]
                assert rows[1]["reviewed_at"] == datetime(2026, 10, 14, 12, tzinfo=UTC)
                with pytest.raises(RuntimeError, match="data inventada"):
                    migration.downgrade()
                connection.execute(
                    text("UPDATE lesson_version SET reviewed_at=:date WHERE id=1"),
                    {"date": datetime(2026, 10, 14, 12, tzinfo=UTC)},
                )
                migration.downgrade()
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(rehearse)
