"""SEC-47: posse, concorrência, consentimento e arquivos após rejeição."""

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.db.models import AssistReservation, DialogueTurn, SpeakingAttempt, SpeakingDialogue
from app.services.audio_upload import MAX_AUDIO_BYTES
from tests.audio_samples import wav
from tests.test_auth import auth, registrar
from tests.test_dialogue_routes import _aula_id, _criar

BASE = "/api/speaking/dialogues"


@pytest.fixture
def guided(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_provider_kind", "gateway")
    monkeypatch.setattr(settings, "assist_dialogue_url", "https://provider.invalid/dialogue")
    monkeypatch.setattr(settings, "assist_dialogue_daily_turns", 12)
    return settings


async def text_turn(client, headers, dialogue_id, position=1, key=None):
    return await client.post(
        f"{BASE}/{dialogue_id}/turns/{position}/text",
        headers=headers,
        json={"text": "I took the train.", "idempotency_key": key or str(uuid4())},
    )


@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("GET", "", None),
        ("GET", "/turns/1", None),
        ("POST", "/turns/1/text", {"text": "Other account", "idempotency_key": str(uuid4())}),
        ("PUT", "/turns/1/rating", {"rating": "helpful"}),
        ("PUT", "/turns/1/audio", None),
        ("DELETE", "", None),
    ],
)
async def test_every_owned_route_hides_other_account(
    client, tmp_path, monkeypatch, method, suffix, body
):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    owner = auth(await registrar(client, "sec-owner"))
    stranger = auth(await registrar(client, "sec-stranger"))
    _, dialogue = await _criar(client, owner)
    assert (await text_turn(client, owner, dialogue["id"])).status_code == 202
    headers = {**stranger, "X-Audio-Consent": "true"}
    if suffix.endswith("audio"):
        headers["Content-Type"] = "audio/wav"
    kwargs = {"content": wav()} if suffix.endswith("audio") else {"json": body}
    response = await client.request(
        method, f"{BASE}/{dialogue['id']}{suffix}", headers=headers, **kwargs
    )
    assert response.status_code == 404, response.text
    intact = await client.get(f"{BASE}/{dialogue['id']}", headers=owner)
    assert intact.json()["turns"][0]["transcript"] == "I took the train."
    assert intact.json()["turns"][0]["human_rating"] is None
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("GET", "", None),
        ("POST", "", {"lesson_id": 1, "mode": "script", "operation_key": str(uuid4())}),
        ("GET", "/1", None),
        ("GET", "/1/turns/1", None),
        ("POST", "/1/turns/1/text", {"text": "Hello", "idempotency_key": str(uuid4())}),
        ("PUT", "/1/turns/1/rating", {"rating": "helpful"}),
        ("PUT", "/1/turns/1/audio", None),
        ("DELETE", "/1", None),
    ],
)
async def test_all_dialogue_routes_require_login(client, method, suffix, body):
    response = await client.request(
        method, BASE + suffix, json=body, headers={"X-Audio-Consent": "true"}
    )
    assert response.status_code == 401


@pytest.mark.parametrize("consent", [None, "false", "1"])
async def test_audio_requires_explicit_consent_before_storage(
    client, tmp_path, monkeypatch, consent
):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers = auth(await registrar(client, "sec-consent"))
    _, dialogue = await _criar(client, headers)
    headers["Content-Type"] = "audio/wav"
    if consent is not None:
        headers["X-Audio-Consent"] = consent
    result = await client.put(
        f"{BASE}/{dialogue['id']}/turns/1/audio", headers=headers, content=wav()
    )
    assert result.status_code == 422
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "kind,status", [("oversized", 413), ("duration", 422), ("invalid", 422), ("mime", 415)]
)
async def test_audio_bounds_before_storage(client, tmp_path, monkeypatch, kind, status, guided):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers = auth(await registrar(client, "sec-bounds"))
    _, dialogue = await _criar(client, headers, mode="guided")
    payload = {
        "oversized": b"x" * (MAX_AUDIO_BYTES + 1),
        "duration": wav(31_000),
        "invalid": b"not audio",
        "mime": wav(),
    }[kind]
    result = await client.put(
        f"{BASE}/{dialogue['id']}/turns/1/audio",
        content=payload,
        headers={
            **headers,
            "X-Audio-Consent": "true",
            "Content-Type": "text/plain" if kind == "mime" else "audio/wav",
        },
    )
    assert result.status_code == status, result.text
    assert not list(tmp_path.iterdir())


async def test_audio_replay_keeps_one_file_and_conflicting_bytes_are_rejected(
    client,
    session,
    tmp_path,
    monkeypatch,
    guided,
):
    monkeypatch.setattr(guided, "speaking_storage_dir", str(tmp_path))
    headers = auth(await registrar(client, "sec-audio"))
    _, dialogue = await _criar(client, headers, mode="guided")
    headers = {**headers, "X-Audio-Consent": "true", "Content-Type": "audio/wav"}
    url = f"{BASE}/{dialogue['id']}/turns/1/audio"
    first = await client.put(url, headers=headers, content=wav())
    replay = await client.put(url, headers=headers, content=wav())
    assert first.status_code == replay.status_code == 202, first.text
    assert first.json() == replay.json()
    assert first.headers["cache-control"] == "private, no-store"
    conflict = await client.put(url, headers=headers, content=wav(1100))
    assert conflict.status_code == 409
    attempt = (await session.scalars(select(SpeakingAttempt))).one()
    assert attempt.consented_at is not None
    assert attempt.audio_sha256 == sha256(wav()).hexdigest()
    assert attempt.integrity_state == "verified"
    assert len(list(tmp_path.iterdir())) == 1
    assert await session.scalar(select(func.count()).select_from(AssistReservation)) == 1


async def test_rejected_audio_leaves_no_file_or_attempt(
    client, session, tmp_path, monkeypatch, guided
):
    monkeypatch.setattr(guided, "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(guided, "assist_dialogue_daily_turns", 1)
    headers = auth(await registrar(client, "sec-orphan"))
    _, dialogue = await _criar(client, headers, mode="guided")
    assert (await text_turn(client, headers, dialogue["id"])).status_code == 202
    result = await client.put(
        f"{BASE}/{dialogue['id']}/turns/2/audio",
        content=wav(),
        headers={**headers, "X-Audio-Consent": "true", "Content-Type": "audio/wav"},
    )
    assert result.status_code == 429, result.text
    assert not list(tmp_path.iterdir())
    assert await session.scalar(select(func.count()).select_from(SpeakingAttempt)) == 0
    assert await session.scalar(select(func.count()).select_from(DialogueTurn)) == 1


async def test_concurrent_admissions_cannot_exceed_quota(client, session, guided):
    headers = auth(await registrar(client, "sec-quota"))
    ids = [(await _criar(client, headers, mode="guided"))[1]["id"] for _ in range(2)]
    results = await asyncio.gather(
        *(text_turn(client, headers, did, pos) for did in ids for pos in range(1, 9))
    )
    assert sorted(r.status_code for r in results) == [202] * 12 + [429] * 4
    assert await session.scalar(select(func.count()).select_from(AssistReservation)) == 12
    assert await session.scalar(select(func.count()).select_from(DialogueTurn)) == 12


async def test_concurrent_replay_and_reused_key_across_dialogues(client, session, guided):
    headers = auth(await registrar(client, "sec-replay"))
    key = str(uuid4())
    payload = {"lesson_id": await _aula_id(client), "mode": "guided", "operation_key": str(uuid4())}
    creations = await asyncio.gather(
        *(client.post(BASE, headers=headers, json=payload) for _ in range(4))
    )
    assert all(r.status_code == 201 for r in creations)
    ids = {r.json()["id"] for r in creations}
    assert len(ids) == 1
    did = ids.pop()
    turns = await asyncio.gather(*(text_turn(client, headers, did, key=key) for _ in range(4)))
    assert all(r.status_code == 202 for r in turns)
    assert len({r.json()["job_id"] for r in turns}) == 1
    _, other = await _criar(client, headers, mode="guided")
    conflict = await text_turn(client, headers, other["id"], key=key)
    assert conflict.status_code == 409, conflict.text
    assert await session.scalar(select(func.count()).select_from(AssistReservation)) == 1
    assert await session.scalar(select(func.count()).select_from(DialogueTurn)) == 1
    changed = await client.post(BASE, headers=headers, json={**payload, "mode": "script"})
    assert changed.status_code == 409


@pytest.mark.parametrize("position,status", [(0, 422), (-1, 422), (51, 422), (13, 409)])
async def test_invalid_turn_positions_do_not_reach_database_constraint(client, position, status):
    headers = auth(await registrar(client, "sec-position"))
    _, dialogue = await _criar(client, headers)
    result = await text_turn(client, headers, dialogue["id"], position)
    assert result.status_code == status, result.text


@pytest.mark.timezone
async def test_private_keyset_history_with_ties_and_foreign_cursor(client, session):
    headers = auth(await registrar(client, "sec-history"))
    stranger = auth(await registrar(client, "sec-history-other"))
    ids = [(await _criar(client, headers))[1]["id"] for _ in range(5)]
    _, foreign = await _criar(client, stranger)
    await session.execute(
        update(SpeakingDialogue).values(started_at=datetime(2026, 1, 1, tzinfo=UTC))
    )
    await session.commit()
    assert (await text_turn(client, headers, ids[-1])).status_code == 202
    received, cursor = [], None
    while True:
        result = await client.get(
            BASE, headers=headers, params={"limit": 2, **({"cursor": cursor} if cursor else {})}
        )
        assert result.status_code == 200, result.text
        assert result.headers["cache-control"] == "private, no-store"
        body = result.json()
        received.extend(item["id"] for item in body["items"])
        assert all("turns" not in item and "transcript" not in item for item in body["items"])
        if cursor is None:
            assert body["items"][0]["turns_remaining"] == 11
            foreign_page = await client.get(
                BASE, headers=stranger, params={"cursor": body["next_cursor"]}
            )
            assert foreign_page.json()["items"] == []
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert received == sorted(ids, reverse=True)
    assert foreign["id"] not in received


@pytest.mark.parametrize(
    "query", [{"limit": 0}, {"limit": 101}, {"cursor": "broken"}, {"cursor": "x" * 257}]
)
async def test_history_rejects_bad_cursor_and_unbounded_pages(client, query):
    headers = auth(await registrar(client, "sec-cursor"))
    assert (await client.get(BASE, headers=headers, params=query)).status_code == 422
