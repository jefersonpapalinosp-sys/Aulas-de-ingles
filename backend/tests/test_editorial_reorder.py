"""40B.2g: audited reorder apply, only inside rollback-only disposable labs."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import cli
from app.core.config import get_settings
from app.db import seed
from app.db.models import (
    CourseReview,
    CourseReviewQuestion,
    EditorialReorderEvent,
    Exercise,
    ExerciseAttempt,
    LessonVersion,
    User,
)
from app.db.seed_plan import read_graph, seed_graph
from app.db.session import get_engine, get_sessionmaker
from app.services import editorial_reorder, publication
from app.services.editorial_reorder_plan import preview_editorial_reorder


def candidate_graph():
    courses = deepcopy(seed.load_course_seed())
    lessons = deepcopy(seed.load_seed())
    lesson = lessons[0]
    first, second = lesson["exercises"][:2]
    first["position"], second["position"] = second["position"], first["position"]
    lesson.update(
        content_version=2,
        editorial_status="reviewed",
        review_note="Reordenação sintética revisada para ensaio isolado.",
        reviewed_at="2026-10-15T12:00:00-03:00",
    )
    return seed_graph(courses, lessons)


def checkpoint_candidate_graph():
    courses = deepcopy(seed.load_course_seed())
    lessons = deepcopy(seed.load_seed())
    review = next(
        unit["review"] for course in courses for unit in course["units"] if unit.get("review")
    )
    first, second = review["questions"][:2]
    first["position"], second["position"] = second["position"], first["position"]
    review["content_version"] += 1
    return seed_graph(courses, lessons)


@pytest.fixture
async def reorder_lab(banco_por_teste, monkeypatch):
    monkeypatch.setattr(get_settings(), "editorial_reorder_enabled", True)
    # Service commits only a SAVEPOINT. Outer rollback removes positions,
    # version and immutable receipt together without disabling its trigger.
    async with get_engine().connect() as connection, connection.begin():
        factory = async_sessionmaker(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield factory
        finally:
            await connection.rollback()


async def proposal(factory, graph=None):
    graph = graph or candidate_graph()
    # Preview uses its own top-level read-only transaction; the apply lab below
    # uses SAVEPOINTs only so all mutations can be rolled back after assertions.
    async with get_sessionmaker()() as session:
        plan = await preview_editorial_reorder(session, graph)
    return (
        graph,
        plan,
        {
            "expected_plan_sha256": plan["plan_sha256"],
            "operation_key": str(uuid4()),
            "operator_label": "synthetic-operator",
            "reason_code": "pedagogical_sequence",
            "confirm_database": "aulas_ingles_test",
        },
    )


async def apply(factory, graph, request):
    async with factory() as session:
        return await editorial_reorder.apply_editorial_reorder(session, graph, **request)


async def test_reorder_is_atomic_audited_idempotent_and_preserves_personal_fk(reorder_lab):
    factory = reorder_lab
    graph, plan, request = await proposal(factory)
    assert plan["allowed"] and plan["counts"]["reordered_entities"] == 2
    changed_keys = [
        (change["editorial_key"],)
        for change in plan["reordered_entities"]
        if change["table"] == "exercise"
    ]
    async with factory() as session:
        stored, ids = await read_graph(session)
        exercise_ids = [ids["exercise"][key] for key in changed_keys]
        affected_lesson_id = ids["lesson"][stored["exercise"][changed_keys[0]]["lesson_id"]]
        before = dict(
            (
                await session.execute(
                    select(Exercise.id, Exercise.position).where(Exercise.id.in_(exercise_ids))
                )
            ).all()
        )
        user = User(
            email="reorder-private@example.test",
            display_name="Synthetic",
            password_hash="unused",
        )
        session.add(user)
        await session.flush()
        session.add(
            ExerciseAttempt(
                user_id=user.id,
                exercise_id=exercise_ids[0],
                idempotency_key=str(uuid4()),
                answer="PRIVATE ANSWER",
                correct=False,
            )
        )
        await session.commit()

    # Personal writes do not invalidate a catalog-only digest, but are counted.
    first = await apply(factory, graph, request)
    assert not first["replayed"] and first["changed_entities"] == 2
    assert (
        first["impact_at_apply"]["personal_direct_references_preserved"][
            "exercise_attempt.exercise_id->exercise.id"
        ]
        == 1
    )
    assert "PRIVATE ANSWER" not in json.dumps(first)
    second = await apply(factory, graph, request)
    assert second == {**first, "replayed": True}

    async with factory() as session:
        after = dict(
            (
                await session.execute(
                    select(Exercise.id, Exercise.position).where(Exercise.id.in_(exercise_ids))
                )
            ).all()
        )
        assert set(after) == set(before) and after != before
        assert {after[row] for row in after} == {before[row] for row in before}
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LessonVersion)
                .where(
                    LessonVersion.lesson_id == affected_lesson_id,
                    LessonVersion.version == 2,
                )
            )
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(EditorialReorderEvent)) == 1
        event = await session.get(EditorialReorderEvent, request["operation_key"])
        assert event is not None and event.db_actor and event.db_login and event.created_at
        for sql in (
            "UPDATE editorial_reorder_event SET impact=impact",
            "DELETE FROM editorial_reorder_event",
        ):
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(text(sql))
    with pytest.raises(ValueError, match="outra solicitação"):
        await apply(factory, graph, {**request, "reason_code": "accessibility_sequence"})


async def test_stale_plan_and_audit_failure_rollback_every_change(reorder_lab, monkeypatch):
    factory = reorder_lab
    graph, _, request = await proposal(factory)
    async with factory() as session:
        await session.execute(
            update(Exercise)
            .where(Exercise.id == select(func.min(Exercise.id)).scalar_subquery())
            .values(prompt="Synthetic changed prompt")
        )
        await session.commit()
    with pytest.raises(ValueError, match="mudou"):
        await apply(factory, graph, request)

    # Restore the synthetic semantic change inside the outer rollback scope,
    # then obtain a fresh valid plan.
    async with factory() as session:
        baseline = seed_graph(seed.load_course_seed(), seed.load_seed())
        original_prompt = next(iter(baseline["exercise"].values()))["prompt"]
        await session.execute(
            update(Exercise)
            .where(Exercise.id == select(func.min(Exercise.id)).scalar_subquery())
            .values(prompt=original_prompt)
        )
        await session.commit()
    graph, _, request = await proposal(factory)
    async with factory() as session:
        stored_before, _ = await read_graph(session)
        await session.rollback()

        async def fail():
            raise RuntimeError("injected receipt failure")

        monkeypatch.setattr(session, "flush", fail)
        with pytest.raises(RuntimeError, match="injected"):
            await editorial_reorder.apply_editorial_reorder(session, graph, **request)
    async with factory() as session:
        stored_after, _ = await read_graph(session)
        assert stored_after == stored_before
        assert await session.scalar(select(func.count()).select_from(EditorialReorderEvent)) == 0


async def test_checkpoint_questions_reorder_with_content_version(reorder_lab):
    factory = reorder_lab
    graph, plan, request = await proposal(factory, checkpoint_candidate_graph())
    assert plan["counts"]["checkpoint_version_bumps"] == 1
    changed = plan["reordered_entities"]
    keys = [(item["editorial_key"],) for item in changed]
    review_key = tuple(plan["checkpoint_version_transitions"][0]["review"])
    async with factory() as session:
        stored, ids = await read_graph(session)
        question_ids = [ids["course_review_question"][key] for key in keys]
        review_id = ids["course_review"][review_key]
        before = dict(
            (
                await session.execute(
                    select(CourseReviewQuestion.id, CourseReviewQuestion.position).where(
                        CourseReviewQuestion.id.in_(question_ids)
                    )
                )
            ).all()
        )
        old_version = stored["course_review"][review_key]["content_version"]
        await session.rollback()
    receipt = await apply(factory, graph, request)
    assert receipt["changed_entities"] == 2
    async with factory() as session:
        after = dict(
            (
                await session.execute(
                    select(CourseReviewQuestion.id, CourseReviewQuestion.position).where(
                        CourseReviewQuestion.id.in_(question_ids)
                    )
                )
            ).all()
        )
        assert after != before and set(after.values()) == set(before.values())
        assert (
            await session.scalar(
                select(CourseReview.content_version).where(CourseReview.id == review_id)
            )
            == old_version + 1
        )


async def test_active_study_admission_blocks_reorder(reorder_lab):
    factory = reorder_lab
    graph, _, request = await proposal(factory)
    async with get_sessionmaker()() as studying:
        await publication.lock_publication(studying)
        with pytest.raises(ValueError, match="ocupado"):
            await apply(factory, graph, request)
        await studying.rollback()
    assert not (await apply(factory, graph, request))["replayed"]


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("confirm_database", "another_database", "Banco não confirmado"),
        ("operation_key", "not-uuid", "UUIDv4"),
        ("operator_label", "operator with private text", "identificador"),
        ("reason_code", "free-form reason", "Motivo"),
        ("expected_plan_sha256", "bad", "plan_sha256"),
    ],
)
async def test_reorder_requires_explicit_valid_confirmation(reorder_lab, field, value, message):
    factory = reorder_lab
    graph, _, request = await proposal(factory)
    with pytest.raises(ValueError, match=message):
        await apply(factory, graph, {**request, field: value})


@pytest.mark.parametrize(
    "setting,value",
    [("editorial_reorder_enabled", False), ("app_env", "prod"), ("deployment_profile", "public")],
)
async def test_reorder_disabled_and_production_rejected(reorder_lab, monkeypatch, setting, value):
    factory = reorder_lab
    graph, _, request = await proposal(factory)
    monkeypatch.setattr(get_settings(), setting, value)
    with pytest.raises(ValueError, match="desativada"):
        await apply(factory, graph, request)


def test_reorder_cli_requires_apply_before_loading_package(monkeypatch):
    called = False

    async def forbidden(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(cli, "_editorial_reorder", forbidden)
    args = [
        "editorial-reorder",
        "--plan-sha256",
        "a" * 64,
        "--operation-key",
        str(uuid4()),
        "--operator",
        "synthetic",
        "--reason",
        "pedagogical_sequence",
        "--confirm-database",
        "aulas_ingles_test",
    ]
    with pytest.raises(SystemExit) as error:
        cli.main_com_argumentos(args)
    assert error.value.code == 2 and not called

    captured = {}

    async def capture(path=None, **kwargs):
        captured.update(path=path, **kwargs)

    monkeypatch.setattr(cli, "_editorial_reorder", capture)
    cli.main_com_argumentos([*args, "--apply"])
    assert captured["expected_plan_sha256"] == "a" * 64
    assert "apply" not in captured


async def test_reorder_migration_append_only_and_safe_downgrade(session):
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/b71d4f9e20c3_editorial_reorder_audit.py"
    )
    spec = importlib.util.spec_from_file_location("reorder_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def rehearse(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA reorder_migration_test"))
            connection.execute(text("SET LOCAL search_path TO reorder_migration_test"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.downgrade()
                migration.upgrade()
                connection.execute(
                    text("""INSERT INTO editorial_reorder_event
                      (operation_key,operator_label,reason_code,plan_sha256,
                       catalog_before_sha256,catalog_candidate_sha256,catalog_after_sha256,
                       changes,impact)
                      VALUES(:key,'test','pedagogical_sequence',:hash,:hash,:hash,:hash,'[]','{}')"""),
                    {"key": str(uuid4()), "hash": "a" * 64},
                )
                with pytest.raises(RuntimeError, match="Preserve reorder audit"):
                    migration.downgrade()
                for sql in (
                    "UPDATE editorial_reorder_event SET impact='{}'",
                    "DELETE FROM editorial_reorder_event",
                ):
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        connection.execute(text(sql))
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(rehearse)
