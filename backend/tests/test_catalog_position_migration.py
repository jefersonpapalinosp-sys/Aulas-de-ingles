"""Contrato da migration que alinha o catalogo inicial ao seed protegido."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


async def test_catalog_position_migration_is_idempotent_and_safe_on_downgrade(session):
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/a42c7d1e9f20_align_level_1_unit_position.py"
    )
    spec = importlib.util.spec_from_file_location("catalog_position_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def exercise(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA catalog_position_migration_test"))
            connection.execute(text("SET LOCAL search_path TO catalog_position_migration_test"))
            connection.execute(
                text(
                    "CREATE TABLE course ("
                    "id integer PRIMARY KEY, slug varchar(100) NOT NULL UNIQUE)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE course_unit ("
                    "id integer PRIMARY KEY, course_id integer NOT NULL, "
                    "slug varchar(100) NOT NULL, position integer NOT NULL, "
                    "UNIQUE (course_id, position))"
                )
            )
            connection.execute(text("INSERT INTO course VALUES (1, 'voa-level-1')"))
            connection.execute(
                text("INSERT INTO course_unit VALUES (10, 1, '31-40', 1)")
            )

            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()
                assert connection.scalar(
                    text("SELECT position FROM course_unit WHERE id=10")
                ) == 7

                migration.downgrade()
                assert connection.scalar(
                    text("SELECT position FROM course_unit WHERE id=10")
                ) == 1

                migration.upgrade()
                connection.execute(
                    text("INSERT INTO course_unit VALUES (11, 1, '1-5', 1)")
                )
                migration.downgrade()
                assert connection.scalar(
                    text("SELECT position FROM course_unit WHERE id=10")
                ) == 7
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(exercise)
