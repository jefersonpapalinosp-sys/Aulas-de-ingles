"""Sprint 38: transações reais em conexões distintas da base descartável."""

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import AuthRateBucket, RefreshSession, ReviewEvent, ReviewItem, StepProgress
from app.main import create_app
from app.services.auth_limits import password_work
from tests.test_auth import auth, credenciais, registrar
from tests.test_writing import proposta


async def draft_path(client):
    prompt = await proposta(client)
    return f"/api/writing/prompts/{prompt['id']}"


async def review_item(client, headers):
    result = await client.put("/api/lessons/31/studied", headers=headers)
    assert result.status_code == 204
    return (await client.get("/api/review/due", headers=headers)).json()[0]


async def test_register_collision_is_409(client, session):
    results = await asyncio.gather(
        *(client.post("/api/auth/register", json=credenciais("collision")) for _ in range(3))
    )
    assert sorted(r.status_code for r in results) == [201, 409, 409]
    assert (await session.scalar(select(func.count()).select_from(RefreshSession))) == 1


async def test_refresh_converges_and_logout_revokes_family(client, session):
    await registrar(client, "concurrent-refresh")
    old = client.cookies.get("refresh_token")
    results = await asyncio.gather(
        *(
            client.post("/api/auth/refresh", headers={"Cookie": f"refresh_token={old}"})
            for _ in range(5)
        )
    )
    assert all(r.status_code == 200 for r in results)
    cookies = {r.cookies.get("refresh_token") for r in results}
    assert len(cookies) == 1 and old not in cookies
    assert (await session.scalar(select(func.count()).select_from(RefreshSession))) == 2
    successor = cookies.pop()
    result = await client.post(
        "/api/auth/refresh", headers={"Cookie": f"refresh_token={successor}"}
    )
    assert result.cookies.get("refresh_token") == successor
    await client.post("/api/auth/logout", headers={"Cookie": f"refresh_token={old}"})
    for cookie in (old, successor):
        assert (
            await client.post("/api/auth/refresh", headers={"Cookie": f"refresh_token={cookie}"})
        ).status_code == 401


async def test_draft_cas_and_version_numbers(client):
    headers = auth(await registrar(client, "draft-concurrency"))
    path = await draft_path(client)
    results = await asyncio.gather(
        *(
            client.post(
                path + "/versions", headers=headers, json={"text": text, "expected_revision": 0}
            )
            for text in ("First draft.", "Second draft.")
        )
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(r.json() for r in results if r.status_code == 200)
    rejected = next(r.json() for r in results if r.status_code == 409)
    assert rejected["detail"]["current"]["text"] == winner["text"]
    assert winner["draft_revision"] == 1
    replay = await client.post(
        path + "/versions", headers=headers, json={"text": winner["text"], "expected_revision": 0}
    )
    assert replay.json() == winner
    second = await client.post(
        path + "/versions",
        headers=headers,
        json={"text": "Chosen resolution.", "expected_revision": 1},
    )
    assert second.json()["version"] == 2
    assert second.json()["draft_revision"] == 2
    other = auth(await registrar(client, "other-draft"))
    assert (await client.get(path + "/draft", headers=other)).json()["text"] == ""


async def test_draft_retry_and_future_revision(client):
    headers = auth(await registrar(client, "draft-retry"))
    path = await draft_path(client)
    body = {"text": "Identical.", "expected_revision": 0}
    first = await client.put(path + "/draft", headers=headers, json=body)
    assert first.status_code == 200
    replay = await client.put(path + "/draft", headers=headers, json=body)
    assert replay.json() == first.json()
    assert (
        await client.put(path + "/draft", headers=headers, json={**body, "expected_revision": 999})
    ).status_code == 409
    feedback = await client.post(path + "/feedback", headers=headers, json=body)
    assert feedback.json()["source_text_hash"] == sha256(body["text"].encode()).hexdigest()


async def test_review_exactly_once_and_fingerprint(client, session):
    headers = auth(await registrar(client, "review-concurrency"))
    item = await review_item(client, headers)
    path = f"/api/review/{item['id']}/grade"
    body = {"quality": 4, "expected_revision": item["revision"], "idempotency_key": str(uuid4())}
    responses = await asyncio.gather(
        *(client.post(path, headers=headers, json=body) for _ in range(6))
    )
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json() == responses[0].json() for r in responses)
    assert responses[0].json()["repetitions"] == 1
    events = (await session.scalars(select(ReviewEvent))).all()
    assert len(events) == 1
    assert events[0].before_state["repetitions"] == 0
    assert events[0].after_state == responses[0].json()
    assert events[0].algorithm_version == "sm2-multimodal-v1"
    different = await client.post(path, headers=headers, json={**body, "quality": 1})
    assert different.status_code == 409
    assert different.json()["detail"]["code"] == "idempotency_key_reused"
    assert (
        await client.post(path, headers=headers, json={**body, "idempotency_key": str(uuid4())})
    ).status_code == 409
    # Mesmo removido, o recibo confirma a operação antiga sem reagendar outro item.
    assert (await client.delete(f"/api/review/{item['id']}", headers=headers)).status_code == 204
    assert (await client.post(path, headers=headers, json=body)).json() == responses[0].json()
    other = auth(await registrar(client, "review-other"))
    assert (await client.post(path, headers=other, json=body)).status_code == 404


async def test_review_two_keys_same_revision_only_one_wins(client):
    headers = auth(await registrar(client, "review-race"))
    item = await review_item(client, headers)
    results = await asyncio.gather(
        *(
            client.post(
                f"/api/review/{item['id']}/grade",
                headers=headers,
                json={
                    "quality": 4,
                    "expected_revision": item["revision"],
                    "idempotency_key": str(uuid4()),
                },
            )
            for _ in range(2)
        )
    )
    assert sorted(r.status_code for r in results) == [200, 409]


async def test_review_state_and_receipt_rollback_together(client, session, monkeypatch):
    headers = auth(await registrar(client, "rollback-review"))
    item = await review_item(client, headers)
    original = AsyncSession.commit

    async def fail_commit(self):
        if any(isinstance(row, ReviewEvent) for row in self.new):
            raise HTTPException(503, "Falha sintética antes do commit.")
        await original(self)

    body = {"quality": 4, "expected_revision": item["revision"], "idempotency_key": str(uuid4())}
    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "commit", fail_commit)
        assert (
            await client.post(f"/api/review/{item['id']}/grade", headers=headers, json=body)
        ).status_code == 503
    assert (await session.scalar(select(func.count()).select_from(ReviewEvent))) == 0
    current = await session.get(ReviewItem, item["id"])
    assert current.repetitions == 0 and current.revision == 0
    assert (
        await client.post(f"/api/review/{item['id']}/grade", headers=headers, json=body)
    ).status_code == 200


async def test_journey_merges_completions_not_stale_navigation(client, session):
    headers = auth(await registrar(client, "journey-race"))
    path = "/api/lessons/31/study-session"
    results = await asyncio.gather(
        *(
            client.put(
                path,
                headers=headers,
                json={"current_step": current, "completed_steps": [done], "expected_revision": 0},
            )
            for current, done in [("assistir", "preparar"), ("praticar", "estudar")]
        )
    )
    assert all(r.status_code == 200 for r in results)
    result = (await client.get(path, headers=headers)).json()
    assert result["completed_steps"] == ["preparar", "estudar"]
    assert result["revision"] == 2
    old_navigation = await client.put(
        path,
        headers=headers,
        json={"current_step": "revisar", "completed_steps": [], "expected_revision": 0},
    )
    assert old_navigation.status_code == 409
    complete = await client.put(
        path,
        headers=headers,
        json={
            "current_step": "revisar",
            "completed_steps": ["preparar", "assistir", "estudar", "praticar", "revisar"],
            "expected_revision": 2,
        },
    )
    assert complete.status_code == 200 and complete.json()["completed_at"]
    steps = (await session.scalars(select(StepProgress))).all()
    assert len(steps) == 5 and all(s.completed_at is not None for s in steps)
    # Repetir o estado confirmado não acumula tempo ou revisões.
    repeat = await client.put(
        path,
        headers=headers,
        json={"current_step": "revisar", "completed_steps": [], "expected_revision": 3},
    )
    assert repeat.json()["revision"] == 3 and len(repeat.json()["completed_steps"]) == 5


async def test_mark_lesson_concurrently_keeps_single_origins(client):
    headers = auth(await registrar(client, "mark-concurrency"))
    results = await asyncio.gather(
        *(client.put("/api/lessons/31/studied", headers=headers) for _ in range(3))
    )
    assert all(r.status_code == 204 for r in results)
    items = (await client.get("/api/review/due", headers=headers)).json()
    assert len({i["id"] for i in items}) == len(items) > 0


async def test_legacy_contract_expires_explicitly(client, monkeypatch):
    headers = auth(await registrar(client, "legacy-expiry"))
    path = await draft_path(client)
    item = await review_item(client, headers)
    monkeypatch.setattr(
        get_settings(), "legacy_writes_until", datetime.now(UTC) - timedelta(days=1)
    )
    assert (
        await client.put(path + "/draft", headers=headers, json={"text": "Old client"})
    ).status_code == 428
    assert (
        await client.put(
            path + "/draft", headers=headers, json={"text": "New client", "expected_revision": 0}
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/review/{item['id']}/grade",
            headers=headers,
            json={"quality": 4, "expected_revision": 0},
        )
    ).status_code == 428
    assert (
        await client.put(
            "/api/lessons/31/study-session",
            headers=headers,
            json={"current_step": "assistir", "completed_steps": []},
        )
    ).status_code == 428


async def test_auth_limits_are_atomic_and_do_not_store_identity(client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_identity_limit", 2)
    payload = {"email": "rate@example.com", "password": "wrong-password-long"}
    results = await asyncio.gather(
        *(client.post("/api/auth/login", json=payload) for _ in range(5))
    )
    assert sorted(r.status_code for r in results) == [401, 401, 429, 429, 429]
    assert all(int(r.headers["retry-after"]) > 0 for r in results if r.status_code == 429)
    buckets = (await session.scalars(select(AuthRateBucket))).all()
    assert len(buckets) == 2 and all(len(b.key) == 64 and b.count == 5 for b in buckets)
    # Registro e login compartilham limite da identidade.
    assert (
        await client.post("/api/auth/register", json={**payload, "display_name": "Rate"})
    ).status_code == 429


async def test_origin_limits_ignore_untrusted_forwarded_header(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_origin_limit", 1)
    assert (
        await client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": "long-password"}
        )
    ).status_code == 401
    result = await client.post(
        "/api/auth/login",
        json={"email": "b@example.com", "password": "long-password"},
        headers={"X-Forwarded-For": "192.0.2.4"},
    )
    assert result.status_code == 429


def test_public_profile_refuses_insecure_configuration():
    with pytest.raises(RuntimeError, match="Perfil público"):
        Settings(deployment_profile="public").validar()
    Settings(
        deployment_profile="public", cookie_secure=True, public_origin="https://study.example.com"
    ).validar()


async def test_public_transport_and_private_headers(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "deployment_profile", "public")
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as public:
        assert (await public.get("/api/health/live")).status_code == 426
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as public:
        response = await public.post("/api/auth/register", json=credenciais("https"))
        assert response.status_code == 201
        assert "Secure" in response.headers["set-cookie"]
        assert response.headers["cache-control"] == "private, no-store"
        assert "max-age=" in response.headers["strict-transport-security"]


async def test_hash_pool_bounded_and_event_loop_responsive():
    import threading
    import time

    active = 0
    peak = 0
    ticks = 0
    mutex = threading.Lock()

    def slow_hash():
        nonlocal active, peak
        with mutex:
            active += 1
            peak = max(peak, active)
        time.sleep(0.08)
        with mutex:
            active -= 1
        return True

    async def probe():
        nonlocal ticks
        for _ in range(10):
            await asyncio.sleep(0.005)
            ticks += 1

    result = await asyncio.gather(*(password_work(slow_hash) for _ in range(6)), probe())
    assert result[:6] == [True] * 6 and ticks == 10 and peak == 2


async def test_real_auth_load_keeps_live_responsive(client):
    import json
    import resource
    import sys
    import time

    from argon2 import PasswordHasher

    await registrar(client, "load-probe")
    credentials = credenciais("load-probe")
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    latency = []

    async def probe():
        for _ in range(12):
            started = time.perf_counter()
            assert (await client.get("/api/live")).status_code == 200
            latency.append((time.perf_counter() - started) * 1000)
            await asyncio.sleep(0.01)

    responses = await asyncio.gather(
        *(client.post("/api/auth/login", json=credentials) for _ in range(8)), probe()
    )
    assert all(result.status_code == 200 for result in responses[:-1])
    assert max(latency) < 1000  # teto de regressão, não SLA de produção
    unit = 1 if sys.platform == "darwin" else 1024
    print(
        "SPRINT38_LOAD="
        + json.dumps(
            {
                "requests": 8,
                "hash_concurrency": get_settings().auth_hash_concurrency,
                "argon_memory_kib_per_hash": PasswordHasher().memory_cost,
                "live_max_ms": round(max(latency), 2),
                "process_maxrss_before_mib": round(before * unit / 1024**2, 2),
                "process_maxrss_after_mib": round(
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * unit / 1024**2, 2
                ),
            }
        )
    )
