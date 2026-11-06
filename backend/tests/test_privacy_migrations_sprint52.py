import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def migration(filename):
    path = Path(__file__).resolve().parents[1] / "alembic/versions" / filename
    spec = importlib.util.spec_from_file_location("privacy_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_index_preflight_accepts_valid_indexes_and_rejects_divergence(session):
    module = migration("e52a1b8c9002_privacy_indexes.py")

    def exercise(connection):
        with Operations.context(MigrationContext.configure(connection)):
            # Repetição após interrupção entre índices: nenhum DDL/commit.
            module.upgrade()
            with connection.begin_nested():
                connection.execute(text("CREATE INDEX s52_wrong ON study_active_interval(user_id)"))
                with pytest.raises(RuntimeError, match="divergente"):
                    module._exists("s52_wrong", "study_active_interval", ["event_id"], None)
                connection.execute(text("DROP INDEX s52_wrong"))

    await (await session.connection()).run_sync(exercise)


async def test_audio_queue_prevents_loss_on_downgrade(session):
    module = migration("d52a1b8c9001_dialogue_audio_cleanup.py")
    await session.execute(
        text("INSERT INTO dialogue_audio_deletion(storage_key) VALUES ('opaque')")
    )

    def exercise(connection):
        with (
            Operations.context(MigrationContext.configure(connection)),
            pytest.raises(RuntimeError, match="pendente"),
        ):
            module.downgrade()

    await (await session.connection()).run_sync(exercise)


@pytest.mark.parametrize("limit,apply", [(0, True), (501, True), (None, True), (1, None)])
async def test_retention_function_rejects_invalid_limits(session, limit, apply):
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        await session.execute(
            text("SELECT aulas_dialogue_audio_retention(:size, :apply)"),
            {"size": limit, "apply": apply},
        )
    await session.rollback()
