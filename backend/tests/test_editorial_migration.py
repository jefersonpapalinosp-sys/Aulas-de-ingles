"""Transactional migration rehearsal in its own schema inside the disposable DB."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def test_editorial_migration_no_backfill_owner_immutability_and_safe_downgrade(session):
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/b40e8cd13597_evidence_content_snapshots.py"
    )
    spec = importlib.util.spec_from_file_location("editorial_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def exercise(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA editorial_migration_test"))
            connection.execute(text("SET LOCAL search_path TO editorial_migration_test"))
            for table, columns in {
                "app_user": "id integer PRIMARY KEY",
                "exercise_attempt": "id integer PRIMARY KEY, user_id integer",
                "practice_session": "id integer PRIMARY KEY, user_id integer",
                "practice_session_item": "id integer PRIMARY KEY, practice_session_id integer",
                "writing_feedback": "id integer PRIMARY KEY, user_id integer",
                "speaking_attempt": "id integer PRIMARY KEY, user_id integer",
                "course_review_attempt": "id integer PRIMARY KEY, user_id integer",
            }.items():
                connection.execute(text(f"CREATE TABLE {table} ({columns})"))
            connection.execute(text("INSERT INTO app_user VALUES (1),(2)"))
            connection.execute(text("INSERT INTO exercise_attempt VALUES (1,1)"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                assert (
                    connection.scalar(text("SELECT count(*) FROM evidence_content_snapshot")) == 0
                )
                insertion = """INSERT INTO evidence_content_snapshot
                    (user_id, exercise_attempt_id, schema_version, content, content_sha256)
                    VALUES (:owner,1,'1.0','{}',:hash)"""
                with pytest.raises(IntegrityError), connection.begin_nested():
                    connection.execute(text(insertion), {"owner": 2, "hash": "a" * 64})
                connection.execute(text(insertion), {"owner": 1, "hash": "a" * 64})
                with pytest.raises(IntegrityError), connection.begin_nested():
                    connection.execute(text("UPDATE evidence_content_snapshot SET content='{}'"))
                with pytest.raises(RuntimeError, match="Preserve snapshots"):
                    migration.downgrade()
                connection.execute(text("DELETE FROM exercise_attempt WHERE id=1"))
                assert (
                    connection.scalar(text("SELECT count(*) FROM evidence_content_snapshot")) == 0
                )
                migration.downgrade()
                assert (
                    connection.scalar(
                        text(
                            "SELECT to_regclass("
                            "'editorial_migration_test.evidence_content_snapshot')"
                        )
                    )
                    is None
                )
                migration.upgrade()
                assert (
                    connection.scalar(text("SELECT count(*) FROM evidence_content_snapshot")) == 0
                )
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(exercise)
