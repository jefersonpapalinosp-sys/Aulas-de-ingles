"""Backfill transacional sobre legado e constraints, sem tocar schema público."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def test_assist_expand_preserves_legacy_and_consumption_after_delete(session):
    path = (
        Path(__file__).resolve().parents[1] / "alembic/versions/f28c6abe1375_assist_reservations.py"
    )
    spec = importlib.util.spec_from_file_location("assist_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def exercise(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA assist_migration_test"))
            connection.execute(text("SET LOCAL search_path TO assist_migration_test"))
            for table, columns in {
                "app_user": "id integer PRIMARY KEY",
                "writing_feedback": "id integer PRIMARY KEY, user_id integer, provider text, "
                "assisted_cost_microusd integer, analysis_mode text, created_at timestamptz",
                "transcription_job": "id integer PRIMARY KEY, user_id integer, "
                "idempotency_key text, cost_microusd integer, status text, "
                "requested_at timestamptz",
            }.items():
                connection.execute(text(f"CREATE TABLE {table} ({columns})"))
            connection.execute(text("INSERT INTO app_user VALUES (1)"))
            connection.execute(
                text(
                    "INSERT INTO writing_feedback VALUES "
                    "(1,1,'gateway',20,'assisted',now()),(2,1,NULL,0,'deterministic',now()),"
                    "(3,1,'gateway',0,'fallback',now())"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO transcription_job VALUES "
                    "(1,1,'existing-provider-key',10,'completed',now()),"
                    "(2,1,'existing-queued-key',0,'queued',now())"
                )
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                assert connection.scalar(text("SELECT count(*) FROM assist_reservation")) == 4
                assert (
                    connection.scalar(text("SELECT sum(cost_microusd) FROM assist_reservation"))
                    == 30
                )
                assert (
                    connection.scalar(
                        text("SELECT count(*) FROM assist_reservation WHERE cost_known")
                    )
                    == 2
                )
                assert (
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM assist_reservation "
                            "WHERE dispatched_at IS NOT NULL"
                        )
                    )
                    == 0
                )
                assert (
                    connection.scalar(
                        text("SELECT assist_reservation_id FROM writing_feedback WHERE id=2")
                    )
                    is None
                )
                assert (
                    connection.scalar(
                        text("SELECT idempotency_key FROM transcription_job WHERE id=1")
                    )
                    == "existing-provider-key"
                )
                for sql in [
                    "UPDATE assist_reservation SET cost_microusd=-1",
                    "UPDATE assist_reservation SET state='completed'",
                    "UPDATE assist_reservation SET modality='unknown'",
                    "UPDATE assist_reservation SET expires_at=created_at",
                    "UPDATE assist_reservation SET request_key='duplicate'",
                    "UPDATE assist_reservation SET provider_key='duplicate'",
                    "UPDATE writing_feedback SET assist_reservation_id="
                    "(SELECT min(id) FROM assist_reservation)",
                    "UPDATE transcription_job SET assist_reservation_id=-1",
                ]:
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        connection.execute(text(sql))
                connection.execute(text("DELETE FROM writing_feedback"))
                connection.execute(text("DELETE FROM transcription_job"))
                assert connection.scalar(text("SELECT count(*) FROM assist_reservation")) == 4
                connection.execute(text("DELETE FROM app_user"))
                assert connection.scalar(text("SELECT count(*) FROM assist_reservation")) == 0
                with pytest.raises(RuntimeError, match="preserve o ledger"):
                    migration.downgrade()
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(exercise)
