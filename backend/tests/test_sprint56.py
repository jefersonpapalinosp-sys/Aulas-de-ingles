"""Contratos de rotação, catálogo e migrations sem perda de dados."""

import importlib.util
import os
import subprocess
import sys
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import security
from app.core.config import Settings, get_settings
from app.db.seed import load_course_seed, load_seed, validate_course_reviews
from tests.test_auth import auth, registrar


async def test_http_refresh_reissues_with_new_key_without_extending_deadline(client, monkeypatch):
    access = await registrar(client, "jwt-s56")
    old_refresh = client.cookies.get("refresh_token")
    deadline = security.ler_token(old_refresh, "refresh")["exp"]
    settings = get_settings()
    monkeypatch.setattr(settings, "jwt_previous_secret", settings.jwt_secret)
    monkeypatch.setattr(settings, "jwt_previous_key_id", settings.jwt_key_id)
    monkeypatch.setattr(
        settings, "jwt_previous_valid_until", datetime.now(UTC) + timedelta(days=31)
    )
    monkeypatch.setattr(settings, "jwt_secret", "new-key-s56-" + "x" * 32)
    monkeypatch.setattr(settings, "jwt_key_id", "next")
    assert (await client.get("/api/auth/me", headers=auth(access))).status_code == 200
    response = await client.post("/api/auth/refresh")
    assert response.status_code == 200
    successor = response.cookies.get("refresh_token")
    assert jwt.get_unverified_header(successor)["kid"] == "next"
    assert security.ler_token(successor, "refresh")["exp"] == deadline
    monkeypatch.setattr(
        settings, "jwt_previous_valid_until", datetime.now(UTC) - timedelta(seconds=1)
    )
    assert (await client.get("/api/auth/me", headers=auth(access))).status_code == 401
    assert (await client.post("/api/auth/refresh")).status_code == 200


async def test_alembic_connection_times_out_on_locked_version_table(session):
    await session.execute(text("LOCK TABLE alembic_version IN ACCESS EXCLUSIVE MODE"))
    env = {
        **os.environ,
        "MIGRATION_LOCK_TIMEOUT_MS": "100",
        "MIGRATION_STATEMENT_TIMEOUT_MS": "1000",
    }
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    assert "lock timeout" in result.stderr
    assert time.monotonic() - started < 8


def migration(filename):
    spec = importlib.util.spec_from_file_location(
        "s56_revision", Path(__file__).resolve().parents[1] / "alembic/versions" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_jwt_rotation_accepts_both_keys_then_retires_old_and_legacy(monkeypatch):
    old = Settings(jwt_secret="o" * 64)
    monkeypatch.setattr(security, "get_settings", lambda: old)
    token, _ = security.criar_token(1, "refresh")
    payload = security.ler_token(token, "refresh")
    legacy = jwt.encode(payload, old.jwt_secret, algorithm="HS256")
    assert jwt.get_unverified_header(token)["kid"] == "legacy"
    current = Settings(
        jwt_secret="n" * 64,
        jwt_key_id="next",
        jwt_previous_secret=old.jwt_secret,
        jwt_previous_key_id="legacy",
        jwt_previous_valid_until=datetime.now(UTC) + timedelta(hours=1),
    )
    current.validar()
    monkeypatch.setattr(security, "get_settings", lambda: current)
    for value in (token, legacy):
        assert security.ler_token(value, "refresh")["sub"] == "1"
    new, _ = security.criar_token(1, "refresh")
    assert jwt.get_unverified_header(new)["kid"] == "next"
    current.jwt_previous_valid_until = datetime.now(UTC) - timedelta(seconds=1)
    for value in (token, legacy):
        with pytest.raises(security.TokenInvalido):
            security.ler_token(value, "refresh")
    assert security.ler_token(new, "refresh")["sub"] == "1"
    for headers in ({"kid": "unknown"}, {"kid": "legacy"}, {"kid": "next", "alg": "HS384"}):
        forged = jwt.encode(payload, current.jwt_secret, algorithm="HS256", headers=headers)
        with pytest.raises(security.TokenInvalido):
            security.ler_token(forged, "refresh")


@pytest.mark.parametrize(
    "values",
    [
        {"jwt_previous_secret": "o" * 32},
        {
            "jwt_previous_secret": "o" * 32,
            "jwt_previous_key_id": "legacy",
            "jwt_previous_valid_until": datetime.now(UTC),
        },
        {
            "jwt_previous_secret": "short",
            "jwt_previous_key_id": "other",
            "jwt_previous_valid_until": datetime.now(UTC),
        },
        {
            "jwt_previous_secret": "o" * 32,
            "jwt_previous_key_id": "other",
            "jwt_previous_valid_until": datetime.now(),
        },
    ],
)
def test_invalid_rotation_configuration_is_refused(values):
    with pytest.raises(RuntimeError):
        Settings(**values).validar()


def test_catalog_requires_explicit_review_overlap_and_keeps_existing_seed():
    courses, lessons = load_course_seed(), load_seed()
    validate_course_reviews(courses, lessons)
    broken = deepcopy(courses)
    unit = next(u for c in broken for u in c["units"] if u.get("review_overlap_lesson_numbers"))
    unit.pop("review_overlap_lesson_numbers")
    with pytest.raises(ValueError, match="sobrepostas"):
        validate_course_reviews(broken, lessons)
    unit["review_overlap_lesson_numbers"] = [True]
    with pytest.raises(ValueError, match="sobrepostas"):
        validate_course_reviews(broken, lessons)


async def test_downgrade_refuses_truncation_before_updates(session):
    module = migration("b84e2c7a9d31_classification_exercises.py")

    def exercise(connection):
        with connection.begin_nested():
            connection.execute(text("CREATE SCHEMA s56_classification"))
            connection.execute(text("SET LOCAL search_path TO s56_classification"))
            connection.execute(text("CREATE TABLE exercise_attempt(answer text)"))
            connection.execute(text("CREATE TABLE exercise_answer(value text)"))
            connection.execute(text("INSERT INTO exercise_attempt VALUES (repeat('x',201))"))
            with (
                Operations.context(MigrationContext.configure(connection)),
                pytest.raises(RuntimeError, match="1 respostas"),
            ):
                module.downgrade()
            assert (
                connection.execute(text("SELECT length(answer) FROM exercise_attempt")).scalar_one()
                == 201
            )

    await (await session.connection()).run_sync(exercise)


async def test_provider_limits_validate_separately_and_do_not_erase_bad_rows(session):
    add = migration("a56b1c8d9004_provider_limits.py")
    validate = migration("b56b1c8d9005_validate_provider_limits.py")

    def exercise(connection):
        with connection.begin_nested():
            connection.execute(text("CREATE SCHEMA s56_provider"))
            connection.execute(text("SET LOCAL search_path TO s56_provider"))
            for ddl in (
                "transcription_job(transcript_text text,words jsonb)",
                "dialogue_turn(transcript text,partner_text text,hints jsonb)",
                "writing_feedback(assisted_summary text,assisted_suggestions jsonb)",
            ):
                connection.execute(text("CREATE TABLE " + ddl))
            connection.execute(text("INSERT INTO transcription_job VALUES (repeat('x',5001),null)"))
            with Operations.context(MigrationContext.configure(connection)):
                add.upgrade()
                with pytest.raises(IntegrityError), connection.begin_nested():
                    validate.upgrade()
                assert (
                    connection.execute(
                        text("SELECT length(transcript_text) FROM transcription_job")
                    ).scalar_one()
                    == 5001
                )
                connection.execute(text("DELETE FROM transcription_job"))
                validate.upgrade()
                for sql in (
                    "INSERT INTO transcription_job VALUES (repeat('x',5001),null)",
                    "INSERT INTO transcription_job VALUES (null,'{}')",
                    "INSERT INTO dialogue_turn VALUES (null,repeat('x',281),'[]')",
                    "INSERT INTO writing_feedback VALUES (repeat('x',1001),null)",
                ):
                    with pytest.raises(IntegrityError), connection.begin_nested():
                        connection.execute(text(sql))

    await (await session.connection()).run_sync(exercise)


async def test_event_bigints_and_downgrade_sequence_guard(session):
    module = migration("c56b1c8d9006_event_bigints.py")

    def exercise(connection):
        with connection.begin_nested():
            connection.execute(text("CREATE SCHEMA s56_events"))
            connection.execute(text("SET LOCAL search_path TO s56_events"))
            connection.execute(text("CREATE TABLE review_event(id serial PRIMARY KEY)"))
            connection.execute(text("CREATE TABLE study_activity_event(id serial PRIMARY KEY)"))
            connection.execute(
                text(
                    "CREATE TABLE study_active_interval(id serial PRIMARY KEY,"
                    "event_id integer REFERENCES study_activity_event)"
                )
            )
            with Operations.context(MigrationContext.configure(connection)):
                connection.execute(text("INSERT INTO review_event(id) VALUES (7)"))
                connection.execute(text("INSERT INTO study_activity_event(id) VALUES (41)"))
                connection.execute(text("INSERT INTO study_active_interval(event_id) VALUES (41)"))
                module.upgrade()
                assert (
                    connection.execute(
                        text("SELECT event_id FROM study_active_interval")
                    ).scalar_one()
                    == 41
                )
                connection.execute(text("INSERT INTO study_activity_event(id) VALUES (2147483648)"))
                connection.execute(
                    text("INSERT INTO study_active_interval(event_id) VALUES (2147483648)")
                )
                with pytest.raises(RuntimeError, match="excedem integer"):
                    module.downgrade()
                connection.execute(text("DELETE FROM study_active_interval"))
                connection.execute(text("DELETE FROM study_activity_event"))
                connection.execute(text("SELECT setval('review_event_id_seq',2147483648)"))
                with pytest.raises(RuntimeError, match="excedem integer"):
                    module.downgrade()
                connection.execute(text("SELECT setval('review_event_id_seq',7)"))
                module.downgrade()

    await (await session.connection()).run_sync(exercise)
