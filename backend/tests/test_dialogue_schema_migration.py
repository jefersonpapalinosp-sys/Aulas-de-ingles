"""DB-45 em schema sintético: constraints, modalidade ampliada e downgrade guardado."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/e3a1c7d9b250_assistente_de_conversa_schema.py"
)
OLD_TABLES = {
    "app_user": "id integer PRIMARY KEY",
    "lesson": "id integer PRIMARY KEY",
    "speaking_attempt": "id integer PRIMARY KEY",
    "transcription_job": "id integer PRIMARY KEY",
    "assist_reservation": (
        "id integer PRIMARY KEY, modality text, "
        "CONSTRAINT ck_assist_modality CHECK (modality IN ('writing','transcription'))"
    ),
}
# `id` explícito: inserts reprovados também consomem a sequência.
DIALOGUE = (
    "INSERT INTO speaking_dialogue (id,user_id,lesson_id,operation_key,mode,state,"
    "content_version,content_fingerprint,rubric_version,turn_limit) VALUES "
    "({id},1,1,'11111111-1111-1111-1111-111111111111','{mode}','active',1,'abc',"
    "'dialogue-prompt-v1',{limit})"
)
TURN = (
    "INSERT INTO dialogue_turn (dialogue_id,user_id,position,role,input_kind,state,expires_at) "
    "VALUES (1,1,{position},'{role}',{input},'pending',now() + interval '30 days')"
)


def _load():
    spec = importlib.util.spec_from_file_location("dialogue_schema_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


async def test_upgrade_enforces_shapes_and_downgrade_only_when_empty(session):
    migration = _load()

    def exercise(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA dialogue_migration_test"))
            connection.execute(text("SET LOCAL search_path TO dialogue_migration_test"))
            for name, columns in OLD_TABLES.items():
                connection.execute(text(f"CREATE TABLE {name} ({columns})"))
            connection.execute(text("INSERT INTO app_user VALUES (1), (2)"))
            connection.execute(text("INSERT INTO lesson VALUES (1)"))
            connection.execute(text("INSERT INTO speaking_attempt VALUES (7)"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                connection.execute(text("INSERT INTO assist_reservation VALUES (1,'conversation')"))
                for sql in (
                    "INSERT INTO assist_reservation VALUES (2,'chat')",
                    DIALOGUE.format(id=90, mode="open_chat", limit=12),
                    DIALOGUE.format(id=91, mode="guided", limit=0),
                    DIALOGUE.format(id=92, mode="guided", limit=51),
                ):
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        connection.execute(text(sql))
                connection.execute(text(DIALOGUE.format(id=1, mode="guided", limit=12)))
                with pytest.raises(IntegrityError), connection.begin_nested():  # chave repetida
                    connection.execute(text(DIALOGUE.format(id=2, mode="script", limit=12)))
                connection.execute(text(TURN.format(position=1, role="partner", input="NULL")))
                connection.execute(text(TURN.format(position=2, role="student", input="'audio'")))
                connection.execute(
                    text("UPDATE dialogue_turn SET speaking_attempt_id=7 WHERE position=2")
                )
                for sql in (
                    TURN.format(position=2, role="student", input="'text'"),
                    TURN.format(position=0, role="student", input="'text'"),
                    TURN.format(position=3, role="student", input="NULL"),
                    TURN.format(position=3, role="partner", input="'text'"),
                    TURN.format(position=3, role="student", input="'video'"),
                    TURN.format(position=3, role="teacher", input="NULL"),
                    "UPDATE dialogue_turn SET confidence=1.5 WHERE position=2",
                    "UPDATE dialogue_turn SET hints='{}'::jsonb WHERE position=2",
                    "UPDATE dialogue_turn SET checks='[]'::jsonb WHERE position=2",
                    "UPDATE dialogue_turn SET state='done' WHERE position=2",
                    "UPDATE dialogue_turn SET cost_microusd=-1 WHERE position=2",
                    "UPDATE dialogue_turn SET expires_at=created_at WHERE position=2",
                    "UPDATE dialogue_turn SET speaking_attempt_id=7 WHERE position=1",
                ):
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        connection.execute(text(sql))
                assert connection.execute(
                    text(
                        "SELECT checks::text, hints::text, fallback, cost_microusd "
                        "FROM dialogue_turn WHERE position=1"
                    )
                ).one() == ("{}", "[]", False, 0)
                # Apagar o áudio preserva o turno; apagar o usuário leva tudo por cascata.
                connection.execute(text("DELETE FROM speaking_attempt WHERE id=7"))
                assert (
                    connection.scalar(
                        text("SELECT speaking_attempt_id FROM dialogue_turn WHERE position=2")
                    )
                    is None
                )
                connection.execute(text("DELETE FROM app_user WHERE id=1"))
                assert connection.scalar(text("SELECT count(*) FROM dialogue_turn")) == 0
                assert connection.scalar(text("SELECT count(*) FROM speaking_dialogue")) == 0
                with pytest.raises(RuntimeError, match="downgrade bloqueado.*1 reservas"):
                    migration.downgrade()
                connection.execute(text("DELETE FROM assist_reservation"))
                migration.downgrade()
                assert connection.scalar(text("SELECT to_regclass('dialogue_turn')")) is None
                assert connection.scalar(text("SELECT to_regclass('speaking_dialogue')")) is None
                with pytest.raises(IntegrityError), connection.begin_nested():
                    connection.execute(
                        text("INSERT INTO assist_reservation VALUES (3,'conversation')")
                    )
                migration.upgrade()
                assert (
                    connection.scalar(text("SELECT to_regclass('speaking_dialogue')")) is not None
                )
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(exercise)
