"""Contrato reversível e restrições da fila de exclusão de conta."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def test_account_deletion_migration_constraints_and_guarded_downgrade(session):
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/f40c2d9a1b73_account_deletion_jobs.py"
    )
    spec = importlib.util.spec_from_file_location("account_deletion_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def exercise(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA account_deletion_migration_test"))
            connection.execute(text("SET LOCAL search_path TO account_deletion_migration_test"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                operation_key = "8df8b963-1c35-4c5e-94cc-592f3d55a4ae"
                connection.execute(
                    text(
                        "INSERT INTO account_deletion_job "
                        "(operation_key,state,file_count,deleted_file_count) "
                        "VALUES (:key,'cleanup_pending',1,0)"
                    ),
                    {"key": operation_key},
                )
                connection.execute(
                    text(
                        "INSERT INTO account_deletion_file "
                        "(job_operation_key,storage_key) VALUES (:key,'opaque.webm')"
                    ),
                    {"key": operation_key},
                )
                for sql in [
                    "UPDATE account_deletion_job SET state='unknown'",
                    "UPDATE account_deletion_job SET deleted_file_count=2",
                    "UPDATE account_deletion_file SET attempt_count=-1",
                ]:
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        connection.execute(text(sql))
                with pytest.raises(RuntimeError, match="recibos de exclusao"):
                    migration.downgrade()
                connection.execute(
                    text("DELETE FROM account_deletion_job WHERE operation_key=:key"),
                    {"key": operation_key},
                )
                assert connection.scalar(text("SELECT count(*) FROM account_deletion_file")) == 0
                migration.downgrade()
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(exercise)
