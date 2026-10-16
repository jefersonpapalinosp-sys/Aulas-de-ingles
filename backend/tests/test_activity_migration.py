"""Ensaio transacional 39A: dados antigos preservados e constraints reais."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def test_activity_expand_preserves_legacy_and_rejects_invalid_intervals(session):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/e17b5fad0264_audio_activity.py"
    spec = importlib.util.spec_from_file_location("activity_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def exercise(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA activity_migration_test"))
            connection.execute(text("SET LOCAL search_path TO activity_migration_test"))
            for table, columns in {
                "app_user": "id integer PRIMARY KEY",
                "lesson": "id integer PRIMARY KEY",
                "media_progress": "id integer PRIMARY KEY, position_seconds float NOT NULL",
                "study_plan": "id integer PRIMARY KEY, weekly_minutes integer NOT NULL",
            }.items():
                connection.execute(text(f"CREATE TABLE {table} ({columns})"))
            connection.execute(text("INSERT INTO app_user VALUES (1)"))
            connection.execute(text("INSERT INTO lesson VALUES (31)"))
            connection.execute(text("INSERT INTO media_progress VALUES (1, 42.5)"))
            connection.execute(text("INSERT INTO study_plan VALUES (1, 90)"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                assert connection.execute(
                    text(
                        "SELECT position_seconds,revision,completed,operation_key "
                        "FROM media_progress"
                    )
                ).one() == (42.5, 0, False, None)
                assert connection.execute(
                    text("SELECT weekly_minutes,timezone FROM study_plan")
                ).one() == (90, "UTC")
                assert connection.scalar(text("SELECT count(*) FROM study_active_interval")) == 0
                connection.execute(
                    text("INSERT INTO study_activity_session VALUES ('session',1,31,now())")
                )
                connection.execute(
                    text(
                        "INSERT INTO study_activity_event "
                        "(user_id,session_id,operation_key,fingerprint,duration_ms,credited_ms) "
                        "VALUES (1,'session','operation','hash',30000,30000)"
                    )
                )
                event_id = connection.scalar(text("SELECT id FROM study_activity_event"))
                for sql in [
                    "UPDATE media_progress SET revision=-1",
                    "UPDATE media_progress SET completed=true",
                    "UPDATE study_activity_event SET duration_ms=30001",
                    "UPDATE study_activity_event SET credited_ms=-1",
                    "UPDATE study_activity_event SET credited_ms=30001",
                    "INSERT INTO study_activity_event "
                    "(user_id,session_id,operation_key,fingerprint,duration_ms,credited_ms) "
                    "VALUES (1,'session','operation','hash',1,1)",
                    "INSERT INTO study_active_interval "
                    "(event_id,user_id,lesson_id,starts_at,ends_at) "
                    f"VALUES ({event_id},1,31,now(),now()+interval '31 seconds')",
                    "INSERT INTO study_active_interval "
                    "(event_id,user_id,lesson_id,starts_at,ends_at) "
                    f"VALUES ({event_id},1,31,now(),now())",
                ]:
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        connection.execute(text(sql))
                with pytest.raises(RuntimeError, match="preserve eventos"):
                    migration.downgrade()
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(exercise)
