"""Regressões de sessão e confirmação de senha contra o banco descartável."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.security import ler_token
from app.db.models import RefreshSession
from app.main import create_app
from app.services import account_deletion
from tests.http_assertions import assert_status
from tests.test_auth import auth, credenciais, registrar


async def test_rotation_and_parallel_grace_never_extend_family_deadline(client, session):
    await registrar(client, "absolute-refresh")
    original = client.cookies.get("refresh_token")
    root = (await session.execute(select(RefreshSession))).scalar_one()
    deadline = root.expires_at
    responses = await asyncio.gather(
        *[
            client.post("/api/auth/refresh", headers={"Cookie": f"refresh_token={original}"})
            for _ in range(3)
        ]
    )
    assert all(response.status_code == 200 for response in responses)
    cookies = {response.cookies.get("refresh_token") for response in responses}
    assert len(cookies) == 1
    successor_cookie = cookies.pop()
    successor_jti = ler_token(successor_cookie, "refresh")["jti"]
    assert ler_token(successor_cookie, "refresh")["exp"] == int(deadline.timestamp())
    await session.execute(
        update(RefreshSession)
        .where(RefreshSession.jti == successor_jti)
        .values(created_at=datetime.now(UTC) - timedelta(seconds=11))
    )
    await session.commit()
    rotated = await client.post(
        "/api/auth/refresh", headers={"Cookie": f"refresh_token={successor_cookie}"}
    )
    assert rotated.status_code == 200
    assert ler_token(rotated.cookies.get("refresh_token"), "refresh")["exp"] == int(
        deadline.timestamp()
    )


@pytest.mark.parametrize("missing_root", [False, True])
async def test_legacy_family_cannot_outlive_root(client, session, missing_root):
    await registrar(client, "legacy-expiry")
    assert_status(await client.post("/api/auth/refresh"))
    root = (
        await session.execute(
            select(RefreshSession).where(RefreshSession.jti == RefreshSession.family_id)
        )
    ).scalar_one()
    if missing_root:
        await session.delete(root)
    else:
        root.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()
    # O JWT descendente ainda está válido, como nas famílias antigas com prazo móvel.
    response = await client.post("/api/auth/refresh")
    assert response.status_code == 401
    sessions = (
        (await session.execute(select(RefreshSession).execution_options(populate_existing=True)))
        .scalars()
        .all()
    )
    assert all(row.revoked_at is not None and row.successor_jti is None for row in sessions)


async def test_deletion_rate_limit_precedes_password_hash_and_keeps_session(client, monkeypatch):
    token = await registrar(client, "delete-limit")
    monkeypatch.setattr(get_settings(), "auth_identity_limit", 2)
    password = AsyncMock(return_value=False)
    monkeypatch.setattr(account_deletion, "password_work", password)
    payload = {
        "operation_key": str(uuid4()),
        "password": "senha-errada",
        "confirmation": "EXCLUIR MINHA CONTA",
    }
    first = await client.request("DELETE", "/api/me/account", headers=auth(token), json=payload)
    assert first.status_code == 403
    assert first.json()["code"] == "password_mismatch"
    limited = await client.request("DELETE", "/api/me/account", headers=auth(token), json=payload)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    assert password.await_count == 1
    assert (await client.get("/api/auth/me", headers=auth(token))).status_code == 200


async def test_replay_revokes_descendants_but_not_another_login(client, session):
    await registrar(client, "family-isolation")
    root_cookie = client.cookies.get("refresh_token")
    first = await client.post("/api/auth/refresh")
    child_cookie = first.cookies.get("refresh_token")
    child_jti = ler_token(child_cookie, "refresh")["jti"]
    await session.execute(
        update(RefreshSession)
        .where(RefreshSession.jti == child_jti)
        .values(created_at=datetime.now(UTC) - timedelta(seconds=11))
    )
    await session.commit()
    grandchild = (await client.post("/api/auth/refresh")).cookies.get("refresh_token")
    credentials = credenciais("family-isolation")
    other = await client.post(
        "/api/auth/login", json={"email": credentials["email"], "password": credentials["password"]}
    )
    other_cookie = other.cookies.get("refresh_token")
    await session.execute(
        update(RefreshSession)
        .where(RefreshSession.jti == ler_token(root_cookie, "refresh")["jti"])
        .values(revoked_at=datetime.now(UTC) - timedelta(seconds=11))
    )
    await session.commit()
    for cookie in (root_cookie, child_cookie, grandchild):
        response = await client.post(
            "/api/auth/refresh", headers={"Cookie": f"refresh_token={cookie}"}
        )
        assert response.status_code == 401
    assert (
        await client.post("/api/auth/refresh", headers={"Cookie": f"refresh_token={other_cookie}"})
    ).status_code == 200


async def test_forwarded_header_does_not_change_direct_client_bucket(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_origin_limit", 1)
    first = await client.post(
        "/api/auth/login", json=credenciais("forged-one"), headers={"X-Forwarded-For": "192.0.2.1"}
    )
    second = await client.post(
        "/api/auth/login", json=credenciais("forged-two"), headers={"X-Forwarded-For": "192.0.2.2"}
    )
    assert first.status_code == 401
    assert second.status_code == 429


@pytest.mark.parametrize(
    "env,profile,expected",
    [
        ("test", "local", 200),
        ("dev", "local", 200),
        ("prod", "local", 404),
        ("test", "public", 404),
    ],
)
async def test_documentation_is_not_published_in_production(monkeypatch, env, profile, expected):
    monkeypatch.setattr(get_settings(), "app_env", env)
    monkeypatch.setattr(get_settings(), "deployment_profile", profile)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as browser:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await browser.get(path)).status_code == expected
        assert (await browser.get("/api/live")).status_code == 200
