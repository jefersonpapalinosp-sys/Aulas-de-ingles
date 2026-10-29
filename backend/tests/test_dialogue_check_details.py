"""FE-47: cobertura histórica, sem reconstrução a partir da aula atual."""

import importlib.util
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text

from app.db.models import DialogueTurn, ReviewItem
from app.domain.dialogue import TurnExpectation, evaluate, evaluation_details
from app.services import dialogue
from tests.test_auth import auth, registrar
from tests.test_dialogue_learning import complete, fixture_dialogue
from tests.test_dialogue_routes import _criar


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("I cancel today", [False, False]),
        ("I can today", [True, False]),
        ("I can go by bus", [True, True]),
        ("I go by a bus", [False, False]),
    ],
)
def test_details_use_same_whole_phrase_rule_as_boolean(spoken, expected):
    expectation = TurnExpectation(target_terms=("can", "by bus"), grammar_patterns=("I can",))
    details = evaluation_details(spoken, expectation)
    assert [item["covered"] for item in details["target_terms"]] == expected
    checks = {check.code: check.passed for check in evaluate(spoken, expectation)}
    assert checks["target_terms_missing"] == any(expected)
    assert checks["grammar_pattern_missing"] == details["grammar_patterns"][0]["covered"]
    assert details["target_terms"][1]["text"] == "by bus"


async def test_completed_replay_keeps_terms_and_patterns_from_evaluated_brief(session, monkeypatch):
    _, _, conversation, brief, calls = await fixture_dialogue(session, monkeypatch)
    brief = replace(brief, target_terms=("don't",), grammar_examples=("I don't",))
    turn = await complete(session, conversation, brief, 3, "I dont share private-12345.")
    expected = {
        "target_terms": [{"text": "don't", "covered": True}],
        "grammar_patterns": [{"text": "I don't", "covered": True}],
    }
    assert turn.check_details == expected
    changed = replace(brief, target_terms=("new term",), grammar_examples=("new pattern",))
    replay = await dialogue.resolve_turn(session, turn, conversation, changed, "different text")
    await session.refresh(turn)
    assert turn.check_details == replay.check_details == expected
    assert len(calls) == 1
    assert "private-12345" not in str(turn.check_details)


@pytest.mark.parametrize("legacy", [False, True])
async def test_review_does_not_reinterpret_previous_miss_with_new_vocabulary(
    session, monkeypatch, legacy
):
    _, _, conversation, brief, _ = await fixture_dialogue(session, monkeypatch)
    first = await complete(
        session, conversation, replace(brief, target_terms=brief.target_terms[:1]), 1
    )
    if legacy:
        first.check_details = None
        await session.flush()
    new_brief = replace(brief, target_terms=brief.target_terms[1:2])
    await complete(session, conversation, new_brief, 2)
    assert await session.scalar(select(func.count()).select_from(ReviewItem)) == 0
    await complete(session, conversation, new_brief, 3)
    cards = (await session.scalars(select(ReviewItem))).all()
    assert len(cards) == 1 and cards[0].vocab_item.term == new_brief.target_terms[0]


async def test_script_get_and_legacy_details_are_persisted_not_rebuilt(client, session):
    headers = auth(await registrar(client, "check-details"))
    _, conversation = await _criar(client, headers)
    lesson_id = conversation["lesson_id"]
    did = conversation["id"]
    accepted = await client.post(
        f"/api/speaking/dialogues/{did}/turns/1/text",
        headers=headers,
        json={"text": "I am practising today.", "idempotency_key": str(uuid4())},
    )
    assert accepted.status_code == 202
    turn = (await session.scalars(select(DialogueTurn))).one()
    original = turn.check_details
    assert original is not None and original["target_terms"]
    # Simula edição editorial após o resultado; o GET não relê os termos atuais.
    vocab = (
        await session.execute(
            text("SELECT id, term FROM vocab_item WHERE lesson_id=:id ORDER BY id LIMIT 1"),
            {"id": lesson_id},
        )
    ).one()
    try:
        await session.execute(
            text("UPDATE vocab_item SET term='Changed term' WHERE id=:id"), {"id": vocab.id}
        )
        await session.commit()
        response = await client.get(f"/api/speaking/dialogues/{did}", headers=headers)
        assert response.json()["turns"][0]["check_details"] == original
        response = await client.get(f"/api/speaking/dialogues/{did}/turns/1", headers=headers)
        assert response.json()["check_details"] == original
        turn.check_details = None
        await session.commit()
        response = await client.get(f"/api/speaking/dialogues/{did}/turns/1", headers=headers)
        assert response.json()["check_details"] is None
    finally:
        await session.rollback()
        await session.execute(
            text("UPDATE vocab_item SET term=:term WHERE id=:id"),
            {"id": vocab.id, "term": vocab.term},
        )
        await session.commit()


async def test_migration_keeps_legacy_null_and_guards_historical_details(session):
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/c92f4a8d710e_dialogue_check_details.py"
    )
    spec = importlib.util.spec_from_file_location("check_details_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def exercise(connection):
        with connection.begin_nested() as savepoint:
            connection.execute(text("CREATE SCHEMA check_details_test"))
            connection.execute(text("SET LOCAL search_path TO check_details_test"))
            connection.execute(
                text("CREATE TABLE dialogue_turn (id int PRIMARY KEY, transcript text)")
            )
            connection.execute(text("INSERT INTO dialogue_turn VALUES (1, 'Legacy text')"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                assert connection.execute(
                    text("SELECT transcript, check_details FROM dialogue_turn")
                ).one() == ("Legacy text", None)
                connection.execute(text("UPDATE dialogue_turn SET check_details='{}'::jsonb"))
                with pytest.raises(RuntimeError, match="downgrade bloqueado"):
                    migration.downgrade()
                connection.execute(text("UPDATE dialogue_turn SET check_details=NULL"))
                migration.downgrade()
                migration.upgrade()
                assert (
                    connection.scalar(text("SELECT transcript FROM dialogue_turn")) == "Legacy text"
                )
            savepoint.rollback()

    await (await session.connection()).run_sync(exercise)
