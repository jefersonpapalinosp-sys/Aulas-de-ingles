"""Ensaio do upgrade com dados antigos em schema transacional de teste."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_migration_preserva_legado_e_recusa_descartar_feedback_versionado(
    session: AsyncSession,
) -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/c95f3d8ba042_writing_rubric_version.py"
    )
    spec = importlib.util.spec_from_file_location("writing_version_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def exercise(connection: Connection) -> None:
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA writing_migration_test"))
            connection.execute(text("SET LOCAL search_path TO writing_migration_test"))
            connection.execute(
                text(
                    "CREATE TABLE writing_feedback (id integer PRIMARY KEY, text text, "
                    "ready boolean, checks jsonb NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO writing_feedback VALUES (1, 'Are you Anna?', false, '[{}]'::jsonb)"
                )
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                row = connection.execute(text("SELECT * FROM writing_feedback")).mappings().one()
                assert row["text"] == "Are you Anna?"
                assert row["ready"] is False
                assert row["checks"] == [{}]
                assert row["algorithm_version"] == "legacy-v1"
                assert row["rubric_version"] is None
                assert row["rubric_snapshot"] is None
                migration.downgrade()  # Base só com legado: roundtrip permitido.
                migration.upgrade()
                connection.execute(
                    text(
                        "INSERT INTO writing_feedback VALUES (2, 'New analysis.', true, '[]', "
                        "'writing-rules-v2', :version, CAST(:snapshot AS jsonb))"
                    ),
                    {"version": "sha256:" + "a" * 64, "snapshot": '{"schema_version": 2}'},
                )
                with pytest.raises(RuntimeError, match="Downgrade bloqueado"):
                    migration.downgrade()
                assert connection.scalar(text("SELECT count(*) FROM writing_feedback")) == 2
        finally:
            # Remove apenas o schema sintético criado neste savepoint e restaura search_path.
            savepoint.rollback()

    await (await session.connection()).run_sync(exercise)
