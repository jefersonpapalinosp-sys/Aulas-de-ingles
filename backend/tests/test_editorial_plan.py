"""Archive preview is bounded to one unit and never writes student/catalog data."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import event, insert, select, text

from app import cli
from app.core.config import get_settings
from app.db.models import Course, Lesson, NotebookEntry, User
from app.db.session import get_engine, get_sessionmaker
from app.services import editorial_plan
from app.services.editorial_plan import preview_unit_archive
from tests.test_course_reviews import LEVEL_1_REVIEW_31_40_URL, attempt_body
from tests.test_practice import conta, create_body
from tests.test_seed_plan import editorial_rows, sequences


async def test_preview_read_only_no_sequence_or_content_changes(session):
    before = await editorial_rows(session)
    counters = await sequences(session)
    await session.rollback()
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", observe)
    try:
        report = await preview_unit_archive(session, "voa-level-1", "31-40")
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert report["dry_run"] and not report["apply_available"]
    assert report["target"]["unit_status"] == "published"
    assert report["editorial_rows"]["lesson"] == 10
    assert report["editorial_rows"]["course_review"] == 1
    assert set(report["personal_rows_preserved"].values()) == {0}
    assert report["snapshot_table_available"]
    assert report["external_checkpoint_dependencies"] >= 1
    assert all(sql.lstrip().split()[0] in {"SELECT", "SET"} for sql in statements)
    assert any("REPEATABLE READ, READ ONLY" in sql for sql in statements)
    assert await editorial_rows(session) == before
    assert await sequences(session) == counters
    await session.rollback()
    repeated = await preview_unit_archive(session, "voa-level-1", "31-40")
    assert repeated["report_sha256"] == report["report_sha256"]


async def test_preview_counts_direct_and_indirect_personal_rows_without_exposing_them(
    client, session, monkeypatch
):
    monkeypatch.setattr(get_settings(), "editorial_snapshots_enabled", True)
    headers = await conta(client, "impact-owner")
    lesson = (await client.get("/api/lessons/31")).json()
    exercise = lesson["exercises"][0]["id"]
    prompt = lesson["writing_prompts"][0]["id"]
    assert (
        await client.post(
            f"/api/exercises/{exercise}/attempt",
            headers=headers,
            json={
                "answer": "PRIVATE ANSWER",
                "idempotency_key": str(uuid4()),
            },
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/writing/prompts/{prompt}/versions",
            headers=headers,
            json={
                "text": "PRIVATE WRITING",
                "expected_revision": 0,
            },
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/writing/prompts/{prompt}/feedback",
            headers=headers,
            json={
                "text": "PRIVATE WRITING",
            },
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/courses/voa-level-1/lessons/31/practice-sessions",
            headers=headers,
            json=create_body(mode="quick"),
        )
    ).status_code == 201
    assert (
        await client.post(
            "/api/speaking/attempts",
            headers=headers,
            json={
                "cue_id": lesson["media"][0]["cues"][0]["id"],
                "consent": True,
                "duration_ms": 1000,
            },
        )
    ).status_code == 201
    review = (await client.get(LEVEL_1_REVIEW_31_40_URL, headers=headers)).json()
    assert (
        await client.post(
            f"{LEVEL_1_REVIEW_31_40_URL}/attempts",
            headers=headers,
            json=attempt_body(review, correct=False),
        )
    ).status_code == 201
    # An identically numbered Level 2 unit and a different Level 1 unit are excluded.
    for course, number in (("voa-level-2", 1), ("voa-level-1", 41)):
        assert (
            await client.post(
                "/api/me/notebook",
                headers=headers,
                json={
                    "course_slug": course,
                    "lesson_number": number,
                    "kind": "note",
                    "content": "OUTSIDE TARGET",
                },
            )
        ).status_code == 201
    report = await preview_unit_archive(session, "voa-level-1", "31-40")
    rows = report["personal_rows_preserved"]
    assert rows["exercise_attempt"] == 1
    assert rows["writing_draft"] == rows["writing_revision"] == rows["writing_feedback"] == 1
    assert rows["practice_session"] == 1 and rows["practice_session_item"] == 5
    assert rows["speaking_attempt"] == rows["course_review_attempt"] == 1
    assert rows["evidence_content_snapshot"] == 9
    assert rows["skill_evidence"] == 2  # no voice evidence until an upload is accepted
    assert rows["notebook_entry"] == 0
    assert report["active_practice_sessions"] == 1
    serialized = json.dumps(report)
    for secret in ("PRIVATE ANSWER", "PRIVATE WRITING", "OUTSIDE TARGET", "exemplo.com"):
        assert secret not in serialized


async def test_preview_snapshot_consistent_during_concurrent_personal_write(session, monkeypatch):
    user_id = await session.scalar(
        insert(User)
        .values(
            email="preview-concurrency@example.test",
            display_name="Synthetic",
            password_hash="unused",
        )
        .returning(User.id)
    )
    lesson_id = await session.scalar(
        select(Lesson.id)
        .join(Course)
        .where(
            Course.slug == "voa-level-1",
            Lesson.number == 31,
        )
    )
    await session.commit()
    original = session.scalar
    inserted = False

    async def scalar(statement, *args, **kwargs):
        nonlocal inserted
        if not inserted and "count(*)" in str(statement):
            inserted = True
            async with get_sessionmaker()() as other:
                await other.execute(
                    insert(NotebookEntry).values(
                        user_id=user_id,
                        lesson_id=lesson_id,
                        kind="note",
                        content="CONCURRENT",
                    )
                )
                await other.commit()
        return await original(statement, *args, **kwargs)

    monkeypatch.setattr(session, "scalar", scalar)
    first = await preview_unit_archive(session, "voa-level-1", "31-40")
    assert inserted and first["personal_rows_preserved"]["notebook_entry"] == 0
    second = await preview_unit_archive(session, "voa-level-1", "31-40")
    assert second["personal_rows_preserved"]["notebook_entry"] == 1
    assert first["report_sha256"] != second["report_sha256"]


async def test_preview_accepts_unmigrated_snapshot_schema_and_reports_omission(
    session, monkeypatch
):
    async def absent(_session):
        return False

    monkeypatch.setattr(editorial_plan, "schema_available", absent)
    report = await preview_unit_archive(session, "voa-level-1", "31-40")
    assert not report["snapshot_table_available"]
    assert "evidence_content_snapshot" not in report["personal_rows_preserved"]


async def test_preview_rejects_missing_target_and_dirty_session(session):
    with pytest.raises(ValueError, match="não encontrado"):
        await preview_unit_archive(session, "missing", "31-40")
    with pytest.raises(ValueError, match="não encontrado"):
        await preview_unit_archive(session, "voa-level-2", "31-40")
    await session.execute(text("SELECT 1"))
    with pytest.raises(ValueError, match="sessão nova"):
        await preview_unit_archive(session, "voa-level-1", "31-40")
    await session.rollback()
    session.add(User(email="pending@example.test", display_name="Pending", password_hash="unused"))
    with pytest.raises(ValueError, match="sessão nova"):
        await preview_unit_archive(session, "voa-level-1", "31-40")
    await session.rollback()


def test_preview_cli(capsys):
    cli.main_com_argumentos(["editorial-plan", "--course", "voa-level-1", "--unit", "31-40"])
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] and not report["apply_available"]
    assert report["editorial_rows"]["lesson"] == 10


@pytest.mark.parametrize("flag", ["--apply", "--force", "--delete", "--archive"])
def test_preview_cli_has_no_mutation_path(monkeypatch, flag):
    async def forbidden(*args):
        pytest.fail("Unknown flag must fail before opening database")

    monkeypatch.setattr(cli, "_editorial_plan", forbidden)
    with pytest.raises(SystemExit) as error:
        cli.main_com_argumentos(
            [
                "editorial-plan",
                "--course",
                "voa-level-1",
                "--unit",
                "31-40",
                flag,
            ]
        )
    assert error.value.code == 2


def test_preview_cli_missing_target_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main_com_argumentos(["editorial-plan", "--course", "missing", "--unit", "31-40"])
    assert error.value.code == 2
    assert "não encontrado" in capsys.readouterr().err


async def test_preview_timeout_releases_transaction_without_partial_report(session, monkeypatch):
    monkeypatch.setattr(editorial_plan, "PREVIEW_TIMEOUT_SECONDS", 0)
    with pytest.raises(TimeoutError):
        await preview_unit_archive(session, "voa-level-1", "31-40")
    assert not session.in_transaction()


def test_preview_timeout_cli_exits_without_leaking_internals(monkeypatch, capsys):
    async def timed_out(*args):
        raise TimeoutError("SECRET CONNECTION")

    monkeypatch.setattr(cli, "_editorial_plan", timed_out)
    with pytest.raises(SystemExit) as error:
        cli.main_com_argumentos(["editorial-plan", "--course", "voa-level-1", "--unit", "31-40"])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == "" and "SECRET" not in output.err
