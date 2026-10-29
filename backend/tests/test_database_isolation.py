"""DB-49: limpeza restrita, commits reais e rollback de conteúdo temporário."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.db.models import (
    AccountDeletionFile,
    AccountDeletionJob,
    AuthRateBucket,
    Course,
    CourseUnit,
    Lesson,
    LessonProgress,
    User,
    WorkerHeartbeat,
)
from app.db.test_safety import UnsafeTestDatabase
from tests import db_isolation


async def seed_fingerprints(session):
    result = {}
    for name in sorted(db_isolation.SEED_TABLES):
        result[name] = (await session.execute(text(
            f'SELECT count(*), md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY id)::text, \'[]\')) '
            f'FROM "public"."{name}" t'
        ))).one()
    return result


async def test_reset_preserves_all_seed_rows_and_clears_committed_independent_data(session):
    baseline = await seed_fingerprints(session)
    sequence = await session.scalar(text("SELECT last_value FROM public.lesson_id_seq"))
    user = User(email="db49@example.com", password_hash="synthetic", display_name="DB49")
    session.add(user)
    await session.flush()
    lesson_id = await session.scalar(select(Lesson.id).limit(1))
    job = AccountDeletionJob(operation_key=str(uuid4()), state="cleanup_pending", file_count=1)
    session.add(job)
    await session.flush()
    session.add_all([
        LessonProgress(user_id=user.id, lesson_id=lesson_id),
        AccountDeletionFile(job_operation_key=job.operation_key, storage_key="db49-synthetic"),
        AuthRateBucket(key="db49", window_start=1, count=1),
        WorkerHeartbeat(name="db49", seen_at=datetime.now(UTC)),
    ])
    await session.commit()

    # A limpeza também alcança dados já confirmados, sem depender de rollback.
    await db_isolation.reset_transient_data(session)
    await session.commit()
    await db_isolation.reset_transient_data(session)
    await session.commit()
    for name in db_isolation.TRANSIENT_TABLES:
        assert await session.scalar(text(f'SELECT count(*) FROM "public"."{name}"')) == 0
    assert await seed_fingerprints(session) == baseline
    assert await session.scalar(text("SELECT last_value FROM public.lesson_id_seq")) == sequence


async def test_restrict_refuses_unknown_dependents_instead_of_cascading(session):
    session.add(User(email="db49-guard@example.com", password_hash="x", display_name="Guard"))
    await session.commit()
    with pytest.raises(DBAPIError) as failure:
        async with session.begin_nested():
            # Mesmo vazia, esta tabela não classificada impede TRUNCATE de app_user.
            await session.execute(text(
                "CREATE TABLE public.db49_seed_guard "
                "(user_id integer REFERENCES public.app_user(id))"
            ))
            await db_isolation.reset_transient_data(session)
    assert failure.value.orig.sqlstate == "0A000"
    assert await session.scalar(select(func.count()).select_from(User)) == 1


async def test_reset_refuses_non_test_environment_before_any_sql(monkeypatch):
    session = AsyncMock()
    with monkeypatch.context() as patch:
        patch.setattr(get_settings(), "app_env", "prod")
        with pytest.raises(UnsafeTestDatabase, match="APP_ENV=test"):
            await db_isolation.reset_transient_data(session)
    session.execute.assert_not_called()


def test_inventory_refuses_missing_classification(monkeypatch):
    monkeypatch.setattr(
        db_isolation, "TRANSIENT_TABLES", db_isolation.TRANSIENT_TABLES - {"app_user"}
    )
    with pytest.raises(RuntimeError, match="classifique"):
        db_isolation.assert_table_inventory()


async def test_catalog_transaction_rolls_back_commit_and_failure_seen_by_api(session):
    baseline = await seed_fingerprints(session)
    await session.commit()
    slug = "db49-rollback"
    with pytest.raises(RuntimeError, match="falha simulada"):
        async with db_isolation.catalog_transaction() as (catalog, client):
            course_id = await catalog.scalar(select(Course.id).where(Course.slug == "voa-level-2"))
            catalog.add(CourseUnit(
                course_id=course_id, slug=slug, title="Unidade temporária", position=999,
                status="planned", lesson_start=31, lesson_end=35, total_lessons=5,
            ))
            await catalog.commit()
            response = await client.get("/api/courses/voa-level-2/curriculum")
            assert response.status_code == 200
            assert any(unit["slug"] == slug for unit in response.json()["units"])
            raise RuntimeError("falha simulada depois do commit")
    assert await session.scalar(select(CourseUnit.id).where(CourseUnit.slug == slug)) is None
    assert await seed_fingerprints(session) == baseline
