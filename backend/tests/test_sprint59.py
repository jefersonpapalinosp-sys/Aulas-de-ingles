"""Catálogo externo, concorrência, privacidade e ausência de progresso VOA implícito."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.listening_seed import seed_listening
from app.db.models import (
    LessonProgress,
    ListeningOperation,
    ListeningProgress,
    ListeningResource,
    SkillEvidence,
)
from app.schemas.listening import ListeningResourceOut
from tests.test_notebook import conta

SLUG = "chegada-ao-hotel"
URL = f"/api/me/listening/progress/{SLUG}"


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "listening_enabled", True)


def mark(state="in_progress", revision=0):
    return {"state": state, "expected_revision": revision, "operation_key": str(uuid4())}


async def test_catalog_is_reconciled_and_reading_does_not_mark_progress(client, session):
    headers = await conta(client, "listening-catalog")
    assert (await client.get("/api/listening/resources")).status_code == 401
    response = await client.get("/api/listening/resources", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    rows = response.json()
    assert len(rows) == len({r["slug"] for r in rows}) == len({r["source_url"] for r in rows}) == 31
    assert all(r["level"] == "A2" and r["mode"] == "external_link" for r in rows)
    assert all("duration" not in r and "questions" not in r for r in rows)
    assert (
        await client.get(f"/api/listening/resources/{SLUG}", headers=headers)
    ).status_code == 200
    assert (
        await client.get("/api/listening/resources/missing", headers=headers)
    ).status_code == 404
    assert (await client.get("/api/me/listening/progress", headers=headers)).json() == []
    for model in (ListeningProgress, ListeningOperation, LessonProgress, SkillEvidence):
        assert await session.scalar(select(func.count()).select_from(model)) == 0


async def test_idempotency_and_old_retry_never_rewind_newer_progress(client, session):
    headers = await conta(client, "listening-idem")
    first = mark()
    one = await client.put(URL, headers=headers, json=first)
    assert one.status_code == 200
    assert one.json()["revision"] == 1
    two = await client.put(URL, headers=headers, json=mark("completed", 1))
    assert two.status_code == 200 and two.json()["state"] == "completed"
    retry = await client.put(URL, headers=headers, json=first)
    assert retry.status_code == 200 and retry.json() == one.json()
    conflict = await client.put(URL, headers=headers, json={**first, "state": "completed"})
    assert conflict.status_code == 409
    stale = await client.put(URL, headers=headers, json=mark())
    assert stale.status_code == 409
    current = (await client.get("/api/me/listening/progress", headers=headers)).json()[0]
    assert current["revision"] == 2 and current["state"] == "completed"
    assert await session.scalar(select(func.count()).select_from(ListeningOperation)) == 2
    reset = await client.put(URL, headers=headers, json=mark("not_started", 2))
    assert reset.status_code == 200 and reset.json()["revision"] == 3


@pytest.mark.parametrize("same_key", [False, True])
async def test_concurrent_initial_marks_serialize(client, session, same_key):
    headers = await conta(client, f"listening-race-{same_key}")
    first = mark()
    second = first if same_key else mark("completed")
    responses = await asyncio.gather(
        *(client.put(URL, headers=headers, json=body) for body in (first, second))
    )
    assert sorted(r.status_code for r in responses) == ([200, 200] if same_key else [200, 409])
    assert await session.scalar(select(func.count()).select_from(ListeningProgress)) == 1
    assert await session.scalar(select(func.count()).select_from(ListeningOperation)) == 1


async def test_isolation_export_and_deletion_even_when_feature_disabled(
    client, session, monkeypatch
):
    alice = await conta(client, "listening-alice")
    bob = await conta(client, "listening-bob")
    body = mark("completed")
    assert (await client.put(URL, headers=alice, json=body)).status_code == 200
    assert (await client.get("/api/me/listening/progress", headers=bob)).json() == []
    assert (await client.put(URL, headers=bob, json=body)).status_code == 200
    monkeypatch.setattr(get_settings(), "listening_enabled", False)
    assert (await client.get("/api/listening/config", headers=alice)).json() == {"enabled": False}
    assert (await client.get("/api/listening/resources", headers=alice)).status_code == 404
    assert (await client.put(URL, headers=alice, json=mark())).status_code == 404
    export = await client.get("/api/me/export", headers=alice)
    assert export.status_code == 200
    data = export.json()
    assert len(data["listening_progress"]) == len(data["listening_operations"]) == 1
    assert data["listening_progress"][0]["completion_kind"] == "self_reported"
    assert data["listening_progress"][0]["source_url"].startswith("https://test-english.com/")
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
    assert await session.scalar(select(func.count()).select_from(ListeningProgress)) == 1
    assert await session.scalar(select(func.count()).select_from(ListeningOperation)) == 1
    assert await session.scalar(select(func.count()).select_from(ListeningResource)) == 31


@pytest.mark.parametrize(
    "body",
    [
        {"state": "completed"},
        mark("invented"),
        mark(revision=-1),
        {**mark(), "operation_key": "invalid"},
        {**mark(), "user_id": 99},
    ],
)
async def test_invalid_marks_rejected(client, body):
    headers = await conta(client, "listening-invalid")
    assert (await client.put(URL, headers=headers, json=body)).status_code == 422


async def test_missing_resource_and_anonymous_write(client):
    assert (await client.put(URL, json=mark())).status_code == 401
    headers = await conta(client, "listening-missing")
    response = await client.put("/api/me/listening/progress/missing", headers=headers, json=mark())
    assert response.status_code == 404


async def test_unavailable_link_preserves_manual_history(catalog_lab):
    session, client = catalog_lab
    row = await session.get(ListeningResource, SLUG)
    row.availability = "unavailable"
    await session.commit()
    headers = await conta(client, "listening-unavailable")
    detail = await client.get(f"/api/listening/resources/{SLUG}", headers=headers)
    assert detail.json()["availability"] == "unavailable"
    assert (await client.put(URL, headers=headers, json=mark("completed"))).status_code == 200


async def test_seed_reapply_preserves_ids_and_progress(client, session):
    headers = await conta(client, "listening-seed")
    assert (await client.put(URL, headers=headers, json=mark())).status_code == 200
    before = (await client.get("/api/listening/resources", headers=headers)).json()
    assert await seed_listening(session) == 31
    await session.commit()
    assert (await client.get("/api/listening/resources", headers=headers)).json() == before
    assert (await client.get("/api/me/listening/progress", headers=headers)).json()[0][
        "revision"
    ] == 1


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://test-english.com/listening/a2/x/",
        "https://test-english.com.evil/listening/a2/x/",
        "https://test-english.com/listening/a2/",
    ],
)
def test_seed_rejects_unsafe_destinations(url):
    with pytest.raises(ValueError):
        ListeningResourceOut.safe_source(url)
