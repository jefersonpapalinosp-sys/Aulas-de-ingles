"""Piloto nativo: correção, integridade editorial, privacidade e concorrência reais."""

import asyncio
import copy
import hashlib
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.db.models import (
    LessonProgress,
    NativeListeningResponse,
    NativeListeningSession,
    NativeListeningVersion,
)
from app.db.native_listening_seed import media_root, seed_native_listening
from app.schemas.native_listening import NativeContent
from tests.test_notebook import conta

HOTEL = "hotel-riverside"
LEISURE = "sabado-com-amigos"


@pytest.fixture(autouse=True)
def native_enabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "listening_native_enabled", True)
    monkeypatch.setattr(get_settings(), "listening_native_preview", True)


async def start(client, headers, slug=HOTEL, version=1, key=None):
    response = await client.post(
        f"/api/listening/native/{slug}/sessions",
        headers=headers,
        json={"version": version, "operation_key": key or str(uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()


def answer(question="stay", selected=None, revision=0, kind="answer", key=None):
    return dict(
        kind=kind,
        question_id=question,
        selected_ids=selected or [],
        expected_revision=revision,
        operation_key=key or str(uuid4()),
    )


async def post(client, headers, row, body):
    return await client.post(
        f"/api/listening/sessions/{row['id']}/responses", headers=headers, json=body
    )


async def test_catalog_has_no_answer_or_transcript_and_audio_is_private(client, session):
    headers = await conta(client, "native-catalog")
    assert (await client.get("/api/listening/native")).status_code == 401
    catalog = await client.get("/api/listening/native", headers=headers)
    assert catalog.status_code == 200
    assert catalog.headers["cache-control"] == "private, no-store"
    rows = catalog.json()
    assert len(rows) == 3 and all(row["preview"] for row in rows)
    assert sum(len(row["questions"]) for row in rows) == 10
    assert all(key not in catalog.text for key in ("answer_ids", "explanation", "transcript"))
    assert next(row for row in rows if row["slug"] == "caminho-ao-museu")["map_description"]
    for row in rows:
        url = f"/api/listening/native/{row['slug']}/versions/1/audio"
        assert (await client.get(url)).status_code == 401
        audio = await client.get(url, headers=headers)
        assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg"
        assert audio.headers["cache-control"] == "private, no-store"
        assert audio.content == (media_root() / f"{row['slug']}-v1.mp3").read_bytes()
    assert await session.scalar(select(func.count()).select_from(LessonProgress)) == 0


async def test_first_answer_score_is_immutable_and_completion_is_explicit(client):
    headers = await conta(client, "native-score")
    row = await start(client, headers)
    assert row["feedback"] == [] and row["transcript"] is None and not row["completed"]
    wrong = await post(client, headers, row, answer(selected=["one"]))
    assert wrong.json()["score"] == 0
    correct = await post(client, headers, row, answer(selected=["two"], revision=1))
    assert correct.json()["score"] == 0
    assert correct.json()["feedback"][-1]["correct"]
    assert not correct.json()["feedback"][-1]["first_response"]
    reveal = await post(client, headers, row, answer("breakfast", revision=2, kind="reveal"))
    assert reveal.json()["feedback"][-1]["answer_ids"] == ["half-seven"]
    for revision, question, selected in [(3, "view", ["garden"]), (4, "checkout", ["eleven"])]:
        final = await post(client, headers, row, answer(question, selected, revision))
        assert final.status_code == 200
    assert final.json()["completed"] and final.json()["score"] == 2
    support = await post(client, headers, row, answer(None, revision=5, kind="transcript"))
    assert support.json()["support_revealed"] and "Receptionist:" in support.json()["transcript"]
    assert support.json()["score"] == 2
    exported = (await client.get("/api/me/export", headers=headers)).json()
    saved = exported["native_listening_sessions"][0]
    assert saved["score"] == support.json()["score"]
    assert saved["completed"] and saved["support_revealed"]
    assert saved["transcript"] == support.json()["transcript"]
    events = exported["native_listening_responses"]
    assert events[0]["first_response"] and not events[0]["correct"]
    assert not events[1]["first_response"] and events[1]["correct"]


async def test_multiselect_order_independent_idempotency_and_stale_revision(client, session):
    headers = await conta(client, "native-multi")
    row = await start(client, headers, LEISURE)
    body = answer("activities", ["lunch", "bike"])
    first = await post(client, headers, row, body)
    assert first.status_code == 200 and first.json()["score"] == 1
    replay = await post(client, headers, row, {**body, "selected_ids": ["bike", "lunch"]})
    assert replay.json() == first.json()
    assert (
        await post(client, headers, row, {**body, "selected_ids": ["film", "swim"]})
    ).status_code == 409
    assert (await post(client, headers, row, answer("meeting", ["park"]))).status_code == 409
    assert await session.scalar(select(func.count()).select_from(NativeListeningResponse)) == 1


@pytest.mark.parametrize(
    "body",
    [
        answer("activities", ["bike", "bike"]),
        answer("activities", ["bike"]),
        answer("activities", ["bike", "unknown"]),
        answer("activities", ["bike", "lunch", "film"]),
        answer("unknown", ["bike"]),
        answer(None, ["bike"], kind="transcript"),
        answer("activities", ["bike"], kind="reveal"),
        answer("activities", kind="transcript"),
        {**answer("activities", ["bike", "lunch"]), "user_id": 99},
    ],
)
async def test_invalid_answers_have_no_effect(client, session, body):
    headers = await conta(client, "native-invalid")
    row = await start(client, headers, LEISURE)
    assert (await post(client, headers, row, body)).status_code == 422
    assert await session.scalar(select(func.count()).select_from(NativeListeningResponse)) == 0


@pytest.mark.parametrize("same_key", [True, False])
async def test_concurrent_responses_and_start_replays(client, session, same_key):
    headers = await conta(client, "native-race")
    key = str(uuid4())
    one, two = await asyncio.gather(*(start(client, headers, key=key) for _ in range(2)))
    assert one["id"] == two["id"]
    body = answer(selected=["two"])
    responses = await asyncio.gather(
        *(
            post(client, headers, one, item)
            for item in (
                body,
                body if same_key else answer(selected=["one"]),
            )
        )
    )
    assert sorted(item.status_code for item in responses) == (
        [200, 200] if same_key else [200, 409]
    )
    assert await session.scalar(select(func.count()).select_from(NativeListeningResponse)) == 1
    conflict = await client.post(
        f"/api/listening/native/{LEISURE}/sessions",
        headers=headers,
        json={"version": 1, "operation_key": key},
    )
    assert conflict.status_code == 409


async def test_account_isolation_export_and_cascade_with_flag_off(client, session, monkeypatch):
    alice = await conta(client, "native-alice")
    bob = await conta(client, "native-bob")
    row = await start(client, alice)
    assert (await post(client, alice, row, answer(selected=["two"]))).status_code == 200
    assert (
        await client.get(f"/api/listening/sessions/{row['id']}", headers=bob)
    ).status_code == 404
    assert (await post(client, bob, row, answer(selected=["two"]))).status_code == 404
    monkeypatch.setattr(get_settings(), "listening_native_enabled", False)
    assert (await client.get("/api/listening/native", headers=alice)).status_code == 404
    data = (await client.get("/api/me/export", headers=alice)).json()
    assert len(data["native_listening_sessions"]) == len(data["native_listening_responses"]) == 1
    assert data["native_listening_sessions"][0]["activity_slug"] == HOTEL
    assert data["native_listening_sessions"][0]["score"] == 1
    assert data["native_listening_responses"][0]["first_response"] is True
    assert "answer_ids" not in json.dumps(data["native_listening_responses"])
    deletion = await client.request(
        "DELETE",
        "/api/me/account",
        headers=alice,
        json={
            "operation_key": str(uuid4()),
            "password": "senha-bem-grande",
            "confirmation": "EXCLUIR MINHA CONTA",
        },
    )
    assert deletion.status_code == 202
    for model in (NativeListeningSession, NativeListeningResponse):
        assert await session.scalar(select(func.count()).select_from(model)) == 0
    assert await session.scalar(select(func.count()).select_from(NativeListeningVersion)) == 3


@pytest.mark.parametrize(
    ("env", "profile"), [("prod", "local"), ("dev", "public"), ("test", "public")]
)
async def test_preview_never_exposes_drafts_in_production(client, monkeypatch, env, profile):
    headers = await conta(client, "native-gate")
    with monkeypatch.context() as patch:
        patch.setattr(get_settings(), "app_env", env)
        patch.setattr(get_settings(), "deployment_profile", profile)
        assert (await client.get("https://test/api/listening/native", headers=headers)).json() == []
        assert (
            await client.get(f"https://test/api/listening/native/{HOTEL}", headers=headers)
        ).status_code == 404
        assert (
            await client.get(
                f"https://test/api/listening/native/{HOTEL}/versions/1/audio", headers=headers
            )
        ).status_code == 404


async def test_versions_are_pinned_and_immutable_and_seed_is_repeatable(catalog_lab):
    session, client = catalog_lab
    headers = await conta(client, "native-versions")
    first = await start(client, headers)
    assert await seed_native_listening(session) == 3
    original = await session.scalar(
        select(NativeListeningVersion).where(NativeListeningVersion.slug == HOTEL)
    )
    content = copy.deepcopy(original.content)
    content.update(version=2, title="A new hotel version")
    session.add(
        NativeListeningVersion(
            slug=HOTEL,
            version=2,
            content=content,
            content_sha256=hashlib.sha256(json.dumps(content).encode()).hexdigest(),
        )
    )
    await session.commit()
    latest = await client.get(f"/api/listening/native/{HOTEL}", headers=headers)
    assert latest.json()["version"] == 2
    saved = await client.get(f"/api/listening/sessions/{first['id']}", headers=headers)
    assert saved.json()["activity"]["version"] == 1
    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(
                text("UPDATE native_listening_version SET version=99 WHERE id=:id"),
                {"id": original.id},
            )
    content["status"] = "published"
    with pytest.raises(ValidationError):
        NativeContent.model_validate(content)


async def test_missing_audio_is_503_without_leaking_path(client, monkeypatch):
    headers = await conta(client, "native-missing-audio")

    def absent(content):
        raise ValueError("secret/internal/path")

    monkeypatch.setattr("app.api.native_listening.media_path", absent)
    response = await client.get(f"/api/listening/native/{HOTEL}/versions/1/audio", headers=headers)
    assert response.status_code == 503 and "secret" not in response.text
