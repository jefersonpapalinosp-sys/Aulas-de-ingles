"""40B.2b.2: identity is explicit, immutable, and independent of ordering/content."""

import importlib.util
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError, InvalidRequestError

from app.db import editorial_identity as identities
from app.db import seed, seed_plan
from app.db.models import Base
from app.db.session import get_engine


@pytest.mark.parametrize("name", identities.TABLES)
def test_stable_keys_distinguish_reorder_from_replacement_and_never_allow_it(name):
    _, before = seed.load_seed_graph()
    after = deepcopy(before)
    key = next(iter(after[name]))
    after[name][key]["position"] += 1000
    report = seed_plan.compare_graphs(after, before)
    assert not report["allowed"]
    assert len(report["changes"]) == 1
    assert report["changes"][0]["key"] == key
    assert report["changes"][0]["operation"] == "change"
    assert report["changes"][0]["fields"] == ["position"]
    # Changing a key is NOT interpreted as an update of the original identity.
    row = after[name].pop(key)
    row["editorial_key"] = str(uuid4())
    after[name][(row["editorial_key"],)] = row
    # Keep references coherent for the deliberate replacement proposal.
    for spec in seed_plan.SPECS:
        for field, parent in spec.refs:
            if parent == name:
                for child in after[spec.name].values():
                    if child[field] == key:
                        child[field] = (row["editorial_key"],)
    report = seed_plan.compare_graphs(after, before)
    assert not report["allowed"]
    operations = {c["operation"] for c in report["changes"] if c["table"] == name}
    assert operations == {"create", "omitted"}


@pytest.mark.parametrize(
    "value",
    [None, "", "position-1", 12, str(uuid4()).upper(), "00000000-0000-0000-0000-000000000000"],
)
def test_seed_rejects_noncanonical_or_missing_identity(value):
    courses, lessons = seed.load_course_seed(), seed.load_seed()
    lessons[0]["exercises"][0]["editorial_key"] = value
    with pytest.raises(ValueError, match="editorial_key"):
        seed_plan.seed_graph(courses, lessons)


def test_seed_requires_explicit_keys_and_rejects_cloning_identity_into_new_parent():
    courses, lessons = seed.load_course_seed(), seed.load_seed()
    del lessons[0]["exercises"][0]["editorial_key"]
    with pytest.raises(ValueError, match="editorial_key"):
        seed_plan.seed_graph(courses, lessons)
    lessons = seed.load_seed()
    lessons[1]["exercises"][0]["editorial_key"] = lessons[0]["exercises"][0]["editorial_key"]
    with pytest.raises(ValueError, match="duplicada"):
        seed_plan.seed_graph(courses, lessons)


async def test_stored_keys_match_seed_and_legacy_projection_is_explicit_read_only(
    session, monkeypatch
):
    stored, original_ids = await seed_plan.read_graph(session)
    await session.rollback()

    async def absent(_session):
        return False

    monkeypatch.setattr(identities, "schema_available", absent)
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", observe)
    try:
        report = await seed.preview_seed(session)
        projected, ids = await seed_plan.read_graph(session)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert projected == stored and ids == original_ids
    assert report["changes"] == []
    assert report["identity_storage"] == "legacy_projection"
    assert not report["allowed"] and "c51f9de246a8" in report["schema_blocker"]
    assert all(s.lstrip().split()[0] in {"SELECT", "SET"} for s in statements)
    assert all("editorial_key" not in s for s in statements)
    _, wanted = seed.load_seed_graph()
    with pytest.raises(ValueError, match="nenhuma escrita"):
        await seed_plan.apply_graph(session, wanted)


@pytest.mark.parametrize("name", identities.TABLES)
async def test_regular_orm_reads_do_not_require_identity_columns(session, name):
    model = next(m.class_ for m in Base.registry.mappers if m.local_table.name == name)
    query = select(model).limit(1)
    assert "editorial_key" not in str(query)
    entity = await session.scalar(query)
    with pytest.raises(InvalidRequestError, match="raiseload"):
        _ = entity.editorial_key
    key = await session.scalar(select(model.editorial_key).where(model.id == entity.id))
    assert identities.validate_key(key) == key


async def test_migration_preserves_rows_references_and_immutable_keys(session):
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/c51f9de246a8_stable_editorial_identity.py"
    )
    spec = importlib.util.spec_from_file_location("identity_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def rehearse(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA identity_migration_test"))
            connection.execute(text("SET LOCAL search_path TO identity_migration_test"))
            for name, columns in {
                "course": "id integer PRIMARY KEY, slug text",
                "course_unit": "id integer PRIMARY KEY, "
                "course_id integer REFERENCES course, slug text",
                "lesson": "id integer PRIMARY KEY, "
                "course_id integer REFERENCES course, number integer",
                "course_review": "id integer PRIMARY KEY, unit_id integer REFERENCES course_unit",
                "course_review_question": "id integer PRIMARY KEY, "
                "review_id integer REFERENCES course_review, position integer, prompt text",
                "exercise": "id integer PRIMARY KEY, "
                "lesson_id integer REFERENCES lesson, position integer, prompt text",
                "writing_prompt": "id integer PRIMARY KEY, "
                "lesson_id integer REFERENCES lesson, position integer, prompt text",
                "vocab_item": "id integer PRIMARY KEY, "
                "lesson_id integer REFERENCES lesson, position integer, term text",
                "lesson_media": "id integer PRIMARY KEY, "
                "lesson_id integer REFERENCES lesson, position integer, source_url text",
                "transcript_cue": "id integer PRIMARY KEY, "
                "media_id integer REFERENCES lesson_media, position integer, text_en text",
                "old_result": "id integer PRIMARY KEY, "
                "exercise_id integer REFERENCES exercise, payload jsonb",
            }.items():
                connection.execute(text(f"CREATE TABLE {name} ({columns})"))
            for statement in (
                "INSERT INTO course VALUES(7,'baseline')",
                "INSERT INTO course_unit VALUES(13,7,'one')",
                "INSERT INTO lesson VALUES(21,7,1)",
                "INSERT INTO course_review VALUES(31,13)",
                "INSERT INTO course_review_question VALUES(51,31,1,'question')",
                "INSERT INTO exercise VALUES(61,21,1,'exercise')",
                "INSERT INTO writing_prompt VALUES(71,21,1,'writing')",
                "INSERT INTO vocab_item VALUES(81,21,1,'study')",
                "INSERT INTO lesson_media VALUES(91,21,1,'https://example.test/audio')",
                "INSERT INTO transcript_cue VALUES(101,91,1,'sound')",
                "INSERT INTO old_result VALUES(1,61,"
                "jsonb_build_object('score',1,'old_text','past'))",
            ):
                connection.execute(text(statement))

            def rows(name):
                return [
                    dict(r)
                    for r in connection.execute(
                        text(f"SELECT * FROM {name} ORDER BY id")
                    ).mappings()
                ]

            before = {name: rows(name) for name in (*identities.TABLES, "old_result")}
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                for name in identities.TABLES:
                    current = rows(name)
                    key = current[0].pop("editorial_key")
                    coordinate = (
                        ("baseline", "one", 1)
                        if name == "course_review_question"
                        else ("baseline", 1, 1, 1)
                        if name == "transcript_cue"
                        else ("baseline", 1, "study")
                        if name == "vocab_item"
                        else ("baseline", 1, 1)
                    )
                    assert str(key) == identities.bootstrap_key(name, *coordinate)
                    assert current == before[name]
                    with (
                        pytest.raises(IntegrityError, match="immutable"),
                        connection.begin_nested(),
                    ):
                        connection.execute(
                            text(f"UPDATE {name} SET editorial_key=gen_random_uuid()")
                        )
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        connection.execute(text(f"UPDATE {name} SET editorial_key=NULL"))
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        columns = ",".join(k for k in rows(name)[0] if k != "id")
                        connection.execute(
                            text(
                                f"INSERT INTO {name}(id,{columns}) "
                                f"SELECT 1000,{columns} FROM {name}"
                            )
                        )
                    connection.execute(
                        text(f"UPDATE {name} SET position=17, editorial_key=editorial_key")
                    )
                    assert str(rows(name)[0]["editorial_key"]) == str(key)
                assert rows("old_result") == before["old_result"]
                with pytest.raises(RuntimeError, match="Preserve editorial identities"):
                    migration.downgrade()
                # Synthetic rows only, inside a rollback-only schema rehearsal.
                for name in (
                    "old_result",
                    "transcript_cue",
                    "lesson_media",
                    "exercise",
                    "writing_prompt",
                    "vocab_item",
                    "course_review_question",
                ):
                    connection.execute(text(f"DELETE FROM {name}"))
                migration.downgrade()
                migration.upgrade()
                connection.execute(
                    text("INSERT INTO exercise(id,lesson_id,position,prompt) VALUES(1,21,1,'new')")
                )
                assert identities.validate_key(str(rows("exercise")[0]["editorial_key"]))
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(rehearse)
