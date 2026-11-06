"""Concorrência, relógio e integridade com fixtures sintéticas."""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import update

from app.core import security
from app.core.config import get_settings
from app.db.models import ReviewItem
from app.services import assist_quota
from app.services.audio_audit import inventory
from tests.test_practice import conta, create_body


async def test_concurrent_practice_same_key_across_lessons_has_one_winner(client):
    headers = await conta(client, "s58-race")
    body = create_body()
    results = await asyncio.gather(
        *(
            client.post(
                f"/api/courses/voa-level-1/lessons/{number}/practice-sessions",
                headers=headers,
                json=body,
            )
            for number in (31, 32)
        )
    )
    assert sorted(r.status_code for r in results) == [201, 409]


async def test_review_ties_have_deterministic_order(client, session):
    headers = await conta(client, "s58-order")
    added = await client.post("/api/review/lessons/31", headers=headers)
    assert added.status_code == 200, added.text
    await session.execute(update(ReviewItem).values(created_at=datetime(2026, 1, 1, tzinfo=UTC)))
    await session.commit()
    response = await client.get("/api/review/items?status=active", headers=headers)
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert len(ids) > 1 and ids == sorted(ids, reverse=True)


def test_jwt_clock_skew_does_not_extend_expiration_or_accept_large_future_iat(monkeypatch):
    fixed = datetime(2026, 11, 5, 12, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is not None else fixed.replace(tzinfo=None)

    monkeypatch.setattr(security, "datetime", Clock)
    monkeypatch.setattr(jwt.api_jwt, "datetime", Clock)
    token, _ = security.criar_token(7, "access", issued_at=fixed + timedelta(seconds=25))
    assert security.ler_token(token, "access")["sub"] == "7"
    for issued, expires in (
        (fixed + timedelta(seconds=31), fixed + timedelta(minutes=10)),
        (fixed - timedelta(minutes=15), fixed - timedelta(seconds=1)),
    ):
        token, _ = security.criar_token(7, "access", issued_at=issued, expires_at=expires)
        with pytest.raises(security.TokenInvalido):
            security.ler_token(token, "access")


async def test_quota_converts_instant_to_utc_and_rejects_naive(session):
    instant = datetime.fromisoformat("2026-11-05T22:00:00-03:00")
    result = await assist_quota.usage(session, 999999, instant)
    assert result.resets_at == datetime(2026, 11, 7, tzinfo=UTC)
    with pytest.raises(ValueError, match="fuso"):
        await assist_quota.usage(session, 999999, instant.replace(tzinfo=None))


async def test_disabled_transcription_is_not_a_temporary_outage(client, monkeypatch):
    headers = await conta(client, "s58-disabled")
    monkeypatch.setattr(get_settings(), "assisted_features_enabled", False)
    response = await client.post("/api/speaking/attempts/1/transcription", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "assist_disabled"


@pytest.mark.skipif(os.name != "posix", reason="auditoria usa descritores POSIX")
def test_audio_same_size_and_unchanged_metadata_requires_matching_second_hash(
    tmp_path, monkeypatch
):
    key = "a" * 32 + ".wav"
    path = tmp_path / key
    path.write_bytes(b"original")
    before = path.stat()
    original_read, original_stat = os.read, os.stat
    changed = False

    def read(fd, size):
        nonlocal changed
        value = original_read(fd, size)
        if not changed:
            path.write_bytes(b"modified")
            changed = True
        return value

    def stat(name, *args, **kwargs):
        return before if name == key else original_stat(name, *args, **kwargs)

    monkeypatch.setattr(os, "read", read)
    monkeypatch.setattr(os, "stat", stat)
    monkeypatch.setattr(os, "fstat", lambda fd: before)
    result = inventory(tmp_path, [], datetime.now(UTC) + timedelta(days=2))
    assert not result["complete"]
    assert result["counts"] == {"changed_protected": 1}
    assert path.read_bytes() == b"modified"
