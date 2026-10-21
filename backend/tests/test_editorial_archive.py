"""Real PostgreSQL, rollback-only archive transactions; never DEV/study mutations."""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import cli
from app.core.config import get_settings
from app.db import seed, seed_plan
from app.db.models import Course, EditorialArchiveEvent, Lesson
from app.db.session import get_engine, get_session, get_sessionmaker
from app.main import create_app
from app.services import editorial_archive, publication
from app.services.editorial_plan import collect_unit_archive
from tests.test_course_reviews import LEVEL_1_REVIEW_31_40_URL, attempt_body
from tests.test_media import position_body
from tests.test_practice import conta, create_body
from tests.test_writing import salvar_rascunho


@pytest.fixture
async def archive_lab(banco_por_teste, monkeypatch):
    monkeypatch.setattr(get_settings(), "editorial_archive_enabled", True)
    # Application commits release SAVEPOINTs, never this outer transaction.
    # Immutable audit receipts AND status changes disappear only by rollback.
    async with get_engine().connect() as connection, connection.begin():
        factory = async_sessionmaker(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        app = create_app()

        async def dependency():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_session] = dependency
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            try:
                yield factory, client
            finally:
                await connection.rollback()


async def proposal(factory, course="voa-level-2", unit="26-30"):
    async with factory() as session:
        plan = await collect_unit_archive(session, course, unit)
    return dict(
        course_slug=course,
        unit_slug=unit,
        expected_catalog_sha256=plan["catalog_sha256"],
        operation_key=str(uuid4()),
        operator_label="synthetic-operator",
        reason_code="editorial_review",
        confirm_database=plan["database"],
    ), plan


async def apply(factory, request):
    async with factory() as session:
        return await editorial_archive.archive_unit(session, **request)


async def test_archive_atomic_audited_idempotent_and_private_data_preserved(
    archive_lab, monkeypatch
):
    factory, client = archive_lab
    monkeypatch.setattr(get_settings(), "editorial_snapshots_enabled", True)
    request, initial_plan = await proposal(factory)
    headers = await conta(client, "archive-transaction")
    lesson = (await client.get("/api/courses/voa-level-2/lessons/26")).json()
    prompt = lesson["writing_prompts"][0]["id"]
    assert (await salvar_rascunho(client, headers, prompt, "Private draft")).status_code == 200
    attempt = await client.post(
        f"/api/exercises/{lesson['exercises'][0]['id']}/attempt",
        headers=headers,
        json={"answer": "PRIVATE RESPONSE", "idempotency_key": str(uuid4())},
    )
    assert attempt.status_code == 200

    async def personal_rows():
        async with factory() as db:
            return {
                name: [
                    dict(row)
                    for row in (await db.execute(select(Course.metadata.tables[name]))).mappings()
                ]
                for name in ("exercise_attempt", "writing_draft", "evidence_content_snapshot")
            }

    before = await personal_rows()
    _, plan = await proposal(factory)
    assert request["expected_catalog_sha256"] == plan["catalog_sha256"]
    assert plan["personal_rows_preserved"] != initial_plan["personal_rows_preserved"]
    assert plan["apply_available"] and plan["external_checkpoint_dependencies"] == 0
    first = await apply(factory, request)
    assert not first["replayed"] and first["after_status"] == "archived"
    second = await apply(factory, request)
    assert second == {**first, "replayed": True}
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(EditorialArchiveEvent)) == 1
        event = await session.get(EditorialArchiveEvent, request["operation_key"])
        assert event.db_actor and event.db_login and event.created_at
        for sql in (
            "UPDATE editorial_archive_event SET reason_code='source_unavailable'",
            "DELETE FROM editorial_archive_event",
        ):
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(text(sql))
    assert (await client.get("/api/courses/voa-level-2/lessons/26")).status_code == 404
    assert (await client.get(f"/api/writing/prompts/{prompt}/draft", headers=headers)).json()[
        "text"
    ] == "Private draft"
    assert (
        await client.post(
            f"/api/writing/prompts/{prompt}/feedback",
            headers=headers,
            json={"text": "New activity"},
        )
    ).status_code == 404
    history = await client.get(
        f"/api/me/history/exercise/{attempt.json()['attempt_id']}/content", headers=headers
    )
    assert history.status_code == 200 and history.json()["status"] == "available"
    assert await personal_rows() == before
    assert "PRIVATE RESPONSE" not in json.dumps(first)
    assert "Private draft" not in json.dumps(first)
    with pytest.raises(ValueError, match="outra solicitação"):
        await apply(factory, {**request, "reason_code": "source_unavailable"})
    # New key cannot masquerade as replay of an already archived unit.
    new_request, _ = await proposal(factory)
    with pytest.raises(ValueError, match="target_not_published"):
        await apply(factory, new_request)


async def test_stale_catalog_and_external_dependencies_block_archive(archive_lab):
    factory, _ = archive_lab
    request, _ = await proposal(factory)
    async with factory() as session:
        await session.execute(update(Lesson).where(Lesson.number == 26).values(title="Changed"))
        await session.commit()
    with pytest.raises(ValueError, match="Catálogo mudou"):
        await apply(factory, request)
    request, plan = await proposal(factory, "voa-level-1", "31-40")
    assert plan["external_checkpoint_dependencies"] > 0
    with pytest.raises(ValueError, match="external_checkpoint_dependencies"):
        await apply(factory, request)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("confirm_database", "another_database", "Banco não confirmado"),
        ("operation_key", "not-uuid", "UUIDv4"),
        ("operator_label", "operator with private text", "identificador"),
        ("reason_code", "free-form reason", "Motivo"),
        ("expected_catalog_sha256", "bad", "catalog_sha256"),
    ],
)
async def test_archive_requires_explicit_valid_confirmation(archive_lab, field, value, message):
    factory, _ = archive_lab
    request, _ = await proposal(factory)
    with pytest.raises(ValueError, match=message):
        await apply(factory, {**request, field: value})


@pytest.mark.parametrize(
    "setting,value",
    [("editorial_archive_enabled", False), ("app_env", "prod"), ("deployment_profile", "public")],
)
async def test_archive_disabled_and_production_rejected(archive_lab, monkeypatch, setting, value):
    factory, _ = archive_lab
    request, _ = await proposal(factory)
    monkeypatch.setattr(get_settings(), setting, value)
    with pytest.raises(ValueError, match="desativado"):
        await apply(factory, request)


async def test_receipt_failure_rolls_back_status_and_releases_lock(archive_lab, monkeypatch):
    factory, _ = archive_lab
    request, _ = await proposal(factory)
    async with factory() as session:

        async def fail():
            raise RuntimeError("injected audit failure")

        monkeypatch.setattr(session, "flush", fail)
        with pytest.raises(RuntimeError, match="injected"):
            await editorial_archive.archive_unit(session, **request)
    async with factory() as session:
        plan = await collect_unit_archive(session, "voa-level-2", "26-30")
        assert plan["target"]["unit_status"] == "published"
        assert await session.scalar(select(func.count()).select_from(EditorialArchiveEvent)) == 0
    assert not (await apply(factory, request))["replayed"]


async def test_admission_blocks_archive_and_seed_until_transaction_ends(archive_lab):
    factory, _ = archive_lab
    request, _ = await proposal(factory)
    async with get_sessionmaker()() as studying:
        await publication.lock_publication(studying)
        with pytest.raises(ValueError, match="ocupado"):
            await apply(factory, request)
        async with factory() as seeding:
            with pytest.raises(ValueError, match="ocupado"):
                await seed.seed_lessons(seeding)
        await studying.rollback()
    assert not (await apply(factory, request))["replayed"]


async def test_archive_exclusive_lock_refuses_all_admission_paths(client, session):
    headers = await conta(client, "admission-lock")
    lesson = (await client.get("/api/lessons/31")).json()
    lesson_id = await session.scalar(
        select(Lesson.id).join(Course).where(Course.slug == "voa-level-1", Lesson.number == 31)
    )
    await session.rollback()
    review = (await client.get(LEVEL_1_REVIEW_31_40_URL, headers=headers)).json()
    prompt = lesson["writing_prompts"][0]["id"]
    media = lesson["media"][0]
    requests = [
        (
            "POST",
            f"/api/exercises/{lesson['exercises'][0]['id']}/attempt",
            {"answer": "x", "idempotency_key": str(uuid4())},
        ),
        ("PUT", f"/api/writing/prompts/{prompt}/draft", {"text": "x"}),
        ("POST", f"/api/writing/prompts/{prompt}/feedback", {"text": "x"}),
        (
            "POST",
            "/api/speaking/attempts",
            {"cue_id": media["cues"][0]["id"], "duration_ms": 1500, "consent": True},
        ),
        ("PUT", f"/api/media/{media['id']}/position", position_body(1)),
        ("POST", f"/api/review/items/{lesson['vocab'][0]['id']}", None),
        ("POST", "/api/review/lessons/31", None),
        ("PUT", "/api/lessons/31/studied", None),
        ("POST", "/api/me/activity/sessions", {"session_id": str(uuid4()), "lesson_id": lesson_id}),
        ("POST", "/api/courses/voa-level-1/lessons/31/practice-sessions", create_body()),
        ("POST", f"{LEVEL_1_REVIEW_31_40_URL}/attempts", attempt_body(review, correct=False)),
        ("POST", "/api/me/notebook", {"lesson_number": 31, "kind": "note", "content": "x"}),
    ]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:n,:k)"),
        {"n": publication.PUBLICATION_LOCK[0], "k": publication.PUBLICATION_LOCK[1]},
    )
    for method, path, body in requests:
        response = await client.request(method, path, json=body, headers=headers)
        assert response.status_code == 503, (path, response.text)
    await session.rollback()
    assert (await client.put("/api/lessons/31/studied", headers=headers)).status_code == 204


async def test_seed_explicit_archive_request_gets_read_only_impact_not_apply(session):
    courses, lessons = seed.load_course_seed(), seed.load_seed()
    unit = next(u for u in courses[0]["units"] if u["slug"] == "31-40")
    unit["status"] = "archived"
    report = await seed_plan.preview_graph(session, seed_plan.seed_graph(courses, lessons))
    assert not report["allowed"] and not report["archive_apply_via_seed"]
    assert len(report["archive_requests"]) == 1
    impact = report["archive_requests"][0]
    assert impact["external_checkpoint_dependencies"] > 0
    assert impact["target"]["unit_status"] == "published"
    assert "personal_rows_preserved" in impact


def test_archive_cli_requires_apply_and_reports_errors_without_sql(monkeypatch, capsys):
    args = [
        "editorial-archive",
        "--course",
        "voa-level-2",
        "--unit",
        "26-30",
        "--catalog-sha256",
        "a" * 64,
        "--operation-key",
        str(uuid4()),
        "--operator",
        "synthetic",
        "--reason",
        "editorial_review",
        "--confirm-database",
        "aulas_ingles_test",
    ]
    with pytest.raises(SystemExit) as error:
        cli.main_com_argumentos(args)
    assert error.value.code == 2

    async def capture(**kwargs):
        assert kwargs["unit_slug"] == "26-30" and "apply" not in kwargs
        raise ValueError("ensaio bloqueado")

    monkeypatch.setattr(cli, "_editorial_archive", capture)
    with pytest.raises(SystemExit):
        cli.main_com_argumentos([*args, "--apply"])
    assert "ensaio bloqueado" in capsys.readouterr().err


async def test_archive_migration_append_only_and_safe_downgrade(session):
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/d62a0ef357b9_editorial_archive_audit.py"
    )
    spec = importlib.util.spec_from_file_location("archive_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def rehearse(connection):
        savepoint = connection.begin_nested()
        try:
            connection.execute(text("CREATE SCHEMA archive_migration_test"))
            connection.execute(text("SET LOCAL search_path TO archive_migration_test"))
            connection.execute(text("CREATE TABLE course_unit(id integer PRIMARY KEY)"))
            connection.execute(text("INSERT INTO course_unit VALUES (1)"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.downgrade()
                migration.upgrade()
                connection.execute(
                    text("""INSERT INTO editorial_archive_event
                  (operation_key,unit_id,course_slug,unit_slug,operator_label,reason_code,
                   before_status,after_status,catalog_sha256,impact)
                  VALUES(:key,1,'synthetic','one','test','editorial_review',
                         'published','archived',:hash,'{}')"""),
                    {"key": str(uuid4()), "hash": "a" * 64},
                )
                with pytest.raises(RuntimeError, match="Preserve archive audit"):
                    migration.downgrade()
                for sql in (
                    "UPDATE editorial_archive_event SET impact='{}'",
                    "DELETE FROM editorial_archive_event",
                    "DELETE FROM course_unit",
                ):
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        connection.execute(text(sql))
        finally:
            savepoint.rollback()

    await (await session.connection()).run_sync(rehearse)
