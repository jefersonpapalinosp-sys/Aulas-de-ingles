"""Preflight e constraints da Sprint 38 em schema sintético, sem tocar estudo."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.concurrency_audit import audit
from app.db.models import Lesson, NotebookEntry, ReviewItem, SkillEvidence, User


async def test_audit_empty_personal_data_reports_counts_only(session):
    report = await audit(session)
    assert len(report) == 24  # 22 da Sprint 38 + origem `dialogue_turn` em revisão e evidência
    assert all(isinstance(count, int) and count == 0 for count in report.values())


async def test_audit_reports_cross_owner_and_missing_sources_without_repair(session):
    owner = User(email="audit-owner@example.com", password_hash="synthetic", display_name="Owner")
    other = User(email="audit-other@example.com", password_hash="synthetic", display_name="Other")
    session.add_all([owner, other])
    await session.flush()
    lesson_id = await session.scalar(select(Lesson.id).limit(1))
    note = NotebookEntry(
        user_id=owner.id, lesson_id=lesson_id, kind="note", content="Private synthetic note"
    )
    session.add(note)
    await session.flush()
    session.add_all(
        [
            ReviewItem(
                user_id=other.id,
                lesson_id=lesson_id,
                item_type="phrase",
                source_type="notebook_entry",
                source_id=note.id,
                source_key="audit-wrong-owner",
                skill="writing",
                prompt="Synthetic",
                answer="Synthetic",
                origin_reason="fixture",
                due_at=datetime.now(UTC),
            ),
            SkillEvidence(
                user_id=owner.id,
                skill="writing",
                source_type="writing_feedback",
                source_id=-1,
                score=0.5,
            ),
            SkillEvidence(
                user_id=owner.id,
                skill="writing",
                source_type="unknown_legacy_source",
                source_id=-1,
                score=0.5,
            ),
        ]
    )
    await session.commit()
    await session.execute(text("SET TRANSACTION READ ONLY"))
    report = await audit(session)
    assert {rule: count for rule, count in report.items() if count} == {
        "review_source_notebook_entry": 1,
        "skill_unknown_source": 1,
        "skill_source_writing_feedback": 1,
    }
    assert "Private" not in str(report) and "@" not in str(report)
    assert await session.scalar(
        select(NotebookEntry.content).where(NotebookEntry.id == note.id)
    ) == ("Private synthetic note")
    assert await session.scalar(select(ReviewItem.source_id)) == note.id


async def test_expand_preflight_preserves_old_data_and_checks(session):
    path = (
        Path(__file__).resolve().parents[1] / "alembic/versions/d06a4e9cb153_concurrent_writes.py"
    )
    spec = importlib.util.spec_from_file_location("concurrent_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def exercise(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA concurrency_migration_test"))
            connection.execute(text("SET LOCAL search_path TO concurrency_migration_test"))
            old_tables = {
                "app_user": "id integer PRIMARY KEY",
                "writing_draft": "id integer PRIMARY KEY, text text",
                "refresh_session": "id integer PRIMARY KEY, jti varchar(32), "
                "revoked_at timestamptz",
                "study_session_progress": "id integer PRIMARY KEY, current_step text, "
                "completed_steps jsonb, total_seconds integer",
                "step_progress": "id integer PRIMARY KEY, step text",
                "review_item": "id integer PRIMARY KEY, interval_days integer, "
                "repetitions integer, lapses integer, ease_factor float",
                "notebook_entry": "id integer PRIMARY KEY, kind text, content text",
                "speaking_attempt": "id integer PRIMARY KEY, status text",
            }
            for name, columns in old_tables.items():
                connection.execute(text(f"CREATE TABLE {name} ({columns})"))
            connection.execute(
                text("INSERT INTO writing_draft VALUES (1, 'Keep my original text.')")
            )
            connection.execute(text("INSERT INTO refresh_session VALUES (1, 'old-jti', NULL)"))
            connection.execute(
                text(
                    "INSERT INTO notebook_entry VALUES "
                    "(1, 'invalid', 'Do not print this private text')"
                )
            )
            with Operations.context(MigrationContext.configure(connection)):
                with pytest.raises(RuntimeError, match="ck_notebook_kind.*1") as failure:
                    migration.upgrade()
                assert "private text" not in str(failure.value)
                # Só nesta fixture: simula correção decidida pelo operador, não pelo upgrade.
                connection.execute(text("UPDATE notebook_entry SET kind='note'"))
                migration.upgrade()
                assert connection.execute(
                    text("SELECT text,revision FROM writing_draft")
                ).one() == (
                    "Keep my original text.",
                    0,
                )
                assert connection.execute(
                    text("SELECT family_id,successor_jti FROM refresh_session")
                ).one() == ("old-jti", None)
                assert connection.scalar(text("SELECT count(*) FROM review_event")) == 0
                for sql in (
                    "UPDATE writing_draft SET revision=-1",
                    "UPDATE notebook_entry SET kind='invalid'",
                    "INSERT INTO study_session_progress VALUES (1,'wrong','[]',0,0)",
                    "INSERT INTO step_progress VALUES (1,'wrong')",
                    "INSERT INTO review_item VALUES (1,-1,0,0,2.5,0)",
                    "INSERT INTO speaking_attempt VALUES (1,'unknown')",
                ):
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        connection.execute(text(sql))
                with pytest.raises(RuntimeError, match="downgrade bloqueado"):
                    migration.downgrade()
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(exercise)
