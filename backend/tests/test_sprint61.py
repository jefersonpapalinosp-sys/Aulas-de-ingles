"""Retomada CAS independente e histórico paginado por usuário/versão."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import NativeListeningPosition
from tests.test_notebook import conta
from tests.test_sprint60 import answer, post, start


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "listening_native_enabled", True)
    monkeypatch.setattr(get_settings(), "listening_native_preview", True)


def position(seconds=18, revision=0, **extra):
    return {
        "position_seconds": seconds,
        "expected_revision": revision,
        "operation_key": str(uuid4()),
        "changed_at": datetime.now(UTC).isoformat(),
        **extra,
    }


async def test_resume_is_idempotent_and_does_not_consume_answer_revision(client):
    headers = await conta(client, "native-position")
    practice = await start(client, headers)
    url = f"/api/listening/sessions/{practice['id']}/position"
    initial = await client.get(url, headers=headers)
    assert initial.json()["revision"] == 0 and initial.json()["position_seconds"] == 0
    assert initial.headers["cache-control"] == "private, no-store"
    body = position()
    saved = await client.put(url, headers=headers, json=body)
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert (await client.put(url, headers=headers, json=body)).json() == saved.json()
    assert (
        await client.put(url, headers=headers, json={**body, "position_seconds": 25})
    ).status_code == 409
    response = await post(client, headers, practice, answer(selected=["two"]))
    assert response.status_code == 200 and response.json()["revision"] == 1
    completed = await client.put(url, headers=headers, json=position(0, 1, completed=True))
    assert completed.status_code == 200 and completed.json()["completed"]
    assert (await client.put(url, headers=headers, json=body)).status_code == 409
    assert (await client.get(url, headers=headers)).json()["position_seconds"] == 0


@pytest.mark.parametrize("same", [True, False])
async def test_position_race_is_serialized(client, session, same):
    headers = await conta(client, "position-race")
    practice = await start(client, headers)
    url = f"/api/listening/sessions/{practice['id']}/position"
    body = position()
    result = await asyncio.gather(
        *(
            client.put(url, headers=headers, json=item)
            for item in (body, body if same else position(25))
        )
    )
    assert sorted(item.status_code for item in result) == ([200, 200] if same else [200, 409])
    assert await session.scalar(select(func.count()).select_from(NativeListeningPosition)) == 1


@pytest.mark.parametrize(
    "body",
    [
        position(-1),
        position(1000),
        position(1, completed=True),
        position(changed_at=(datetime.now(UTC) + timedelta(hours=2)).isoformat()),
        position(user_id=99),
        position(1, -1),
    ],
)
async def test_invalid_position_rejected(client, body):
    headers = await conta(client, "position-invalid")
    practice = await start(client, headers)
    result = await client.put(
        f"/api/listening/sessions/{practice['id']}/position", headers=headers, json=body
    )
    assert result.status_code == 422


async def test_history_pagination_scores_and_privacy(client):
    alice = await conta(client, "history-a")
    bob = await conta(client, "history-b")
    first = await start(client, alice)
    await post(client, alice, first, answer(selected=["one"]))
    await post(client, alice, first, answer(selected=["two"], revision=1))
    await post(client, alice, first, answer(None, revision=2, kind="transcript"))
    second = await start(client, alice, "sabado-com-amigos")
    await start(client, bob)
    response = await client.get("/api/listening/history?limit=1", headers=alice)
    assert response.status_code == 200
    page = response.json()
    assert page["attempts"] == 2 and page["first_attempt_at"] and page["last_attempt_at"]
    assert page["items"][0]["session_id"] == second["id"]
    assert page["next_before"] == second["id"]
    third = await start(client, alice)
    next_page = (
        await client.get(
            f"/api/listening/history?limit=1&before={page['next_before']}", headers=alice
        )
    ).json()
    item = next_page["items"][0]
    assert item["session_id"] == first["id"] != third["id"]
    assert item["first_score"] == 0 and item["latest_score"] == 1 and item["support_revealed"]
    assert item["answered"] == 1 and not item["completed"]
    assert next_page["next_before"] is None
    assert not any(key in response.text for key in ("transcript", "answer_ids", "selected_ids"))
    filtered = (
        await client.get("/api/listening/history?slug=sabado-com-amigos", headers=alice)
    ).json()
    assert filtered["attempts"] == 1
    assert (await client.get("/api/listening/history", headers=bob)).json()["attempts"] == 1
    assert (await client.get("/api/listening/history")).status_code == 401
    assert (await client.get("/api/listening/history?limit=51", headers=alice)).status_code == 422


async def test_position_export_and_cascade_with_feature_disabled(client, session, monkeypatch):
    alice = await conta(client, "resume-private-a")
    bob = await conta(client, "resume-private-b")
    practice = await start(client, alice)
    url = f"/api/listening/sessions/{practice['id']}/position"
    assert (await client.put(url, headers=alice, json=position())).status_code == 200
    assert (await client.get(url, headers=bob)).status_code == 404
    assert (await client.put(url, headers=bob, json=position())).status_code == 404
    monkeypatch.setattr(get_settings(), "listening_native_enabled", False)
    assert (await client.get("/api/listening/history", headers=alice)).status_code == 404
    data = (await client.get("/api/me/export", headers=alice)).json()
    assert data["native_listening_positions"][0]["position_seconds"] == 18
    assert "fingerprint" not in data["native_listening_positions"][0]
    response = await client.request(
        "DELETE",
        "/api/me/account",
        headers=alice,
        json={
            "operation_key": str(uuid4()),
            "password": "senha-bem-grande",
            "confirmation": "EXCLUIR MINHA CONTA",
        },
    )
    assert response.status_code == 202
    assert await session.scalar(select(func.count()).select_from(NativeListeningPosition)) == 0
