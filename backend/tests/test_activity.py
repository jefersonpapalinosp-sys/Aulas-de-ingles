"""Tempo ativo: idempotência, sobreposição global e calendário no servidor."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.api.activity import uncovered
from app.db.models import StudyActiveInterval, StudyActivitySession
from tests.test_dashboard import conta


async def activity(client, session, headers, *, course="voa-level-1", number=31, start=None):
    lesson = (await client.get(f"/api/courses/{course}/lessons/{number}")).json()
    body = {"session_id": str(uuid4()), "lesson_id": lesson["id"]}
    response = await client.post("/api/me/activity/sessions", headers=headers, json=body)
    assert response.status_code == 200, response.text
    row = await session.get(StudyActivitySession, body["session_id"])
    row.started_at = start or datetime.now(UTC) - timedelta(minutes=5)
    await session.commit()
    return body


def event(sid, end=30000, duration=30000):
    return {
        "session_id": sid,
        "operation_key": str(uuid4()),
        "end_offset_ms": end,
        "duration_ms": duration,
    }


def test_uncovered_subtracts_nested_and_partial_ranges():
    start = datetime(2026, 10, 14, tzinfo=UTC)
    t = lambda seconds: start + timedelta(seconds=seconds)  # noqa: E731
    assert uncovered(
        t(0), t(30), [(t(-5), t(5)), (t(4), t(10)), (t(15), t(20)), (t(18), t(40))]
    ) == [(t(10), t(15))]


async def test_sessions_are_idempotent_and_private(client, session):
    ana = await conta(client, "activity-ana")
    body = await activity(client, session, ana)
    first = await client.post("/api/me/activity/sessions", headers=ana, json=body)
    second = await client.post("/api/me/activity/sessions", headers=ana, json=body)
    assert first.json()["started_at"] == second.json()["started_at"]
    assert first.json()["server_now"] >= first.json()["started_at"]
    bruno = await conta(client, "activity-bruno")
    assert (
        await client.post("/api/me/activity/sessions", headers=bruno, json=body)
    ).status_code == 409
    assert (
        await client.post("/api/me/activity/events", headers=bruno, json=event(body["session_id"]))
    ).status_code == 404
    assert (
        await client.post("/api/me/activity/events", json=event(body["session_id"]))
    ).status_code == 401
    assert (
        await client.post(
            "/api/me/activity/sessions",
            headers=ana,
            json={"session_id": str(uuid4()), "lesson_id": 999999},
        )
    ).status_code == 404


async def test_event_replay_and_concurrent_overlap_across_courses(client, session):
    headers = await conta(client, "activity-overlap")
    start = datetime.now(UTC) - timedelta(minutes=5)
    one = await activity(client, session, headers, start=start)
    two = await activity(client, session, headers, course="voa-level-2", number=1, start=start)
    body = event(one["session_id"])
    first, second = await asyncio.gather(
        *[client.post("/api/me/activity/events", headers=headers, json=body) for _ in range(2)]
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["credited_ms"] == 30000
    conflict = await client.post(
        "/api/me/activity/events", headers=headers, json={**body, "duration_ms": 10000}
    )
    assert conflict.status_code == 409
    results = await asyncio.gather(
        *[
            client.post("/api/me/activity/events", headers=headers, json=event(sid, 45000))
            for sid in [one["session_id"], two["session_id"]]
        ]
    )
    assert all(r.status_code == 200 for r in results)
    assert sorted(r.json()["credited_ms"] for r in results) == [0, 15000]
    seconds = await session.scalar(
        select(
            func.sum(
                func.extract("epoch", StudyActiveInterval.ends_at - StudyActiveInterval.starts_at)
            )
        )
    )
    assert float(seconds) == 45
    exported = (await client.get("/api/me/export", headers=headers)).json()
    assert exported["schema_version"] == "2.1"
    assert len(exported["activity_sessions"]) == 2
    assert len(exported["activity_events"]) == 3
    assert len(exported["active_intervals"]) == 2
    other = await conta(client, "activity-export-other")
    other_export = (await client.get("/api/me/export", headers=other)).json()
    assert other_export["activity_events"] == []
    assert other_export["active_intervals"] == []


@pytest.mark.parametrize(
    "end,duration", [(500, 1000), (86400001, 10), (30001, 30001), (1, 0), (600000, 1000)]
)
async def test_invalid_or_future_activity_is_rejected(client, session, end, duration):
    headers = await conta(client, "activity-invalid")
    body = await activity(client, session, headers)
    response = await client.post(
        "/api/me/activity/events", headers=headers, json=event(body["session_id"], end, duration)
    )
    assert response.status_code == 422


async def test_offline_replay_expires_but_confirmed_receipt_remains(client, session):
    headers = await conta(client, "activity-expiry")
    body = await activity(client, session, headers)
    recorded = event(body["session_id"])
    assert (
        await client.post("/api/me/activity/events", headers=headers, json=recorded)
    ).status_code == 200
    row = await session.get(StudyActivitySession, body["session_id"])
    row.started_at -= timedelta(days=8)
    await session.commit()
    assert (
        await client.post("/api/me/activity/events", headers=headers, json=recorded)
    ).status_code == 200
    assert (
        await client.post(
            "/api/me/activity/events", headers=headers, json=event(body["session_id"], 60000)
        )
    ).status_code == 410


async def test_week_clips_intervals_uses_timezone_and_ignores_legacy(client, session, monkeypatch):
    from app.api import activity as activity_api
    from app.api import dashboard
    from app.db.models import StudySessionProgress, User

    now = datetime(2026, 10, 14, 12, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(activity_api, "datetime", Clock)
    monkeypatch.setattr(dashboard, "datetime", Clock)
    headers = await conta(client, "activity-week")
    plan = {
        "weekly_minutes": 90,
        "preferred_days": ["mon"],
        "goal": "Study",
        "timezone": "America/Sao_Paulo",
    }
    assert (await client.put("/api/me/study-plan", headers=headers, json=plan)).status_code == 200
    assert (
        await client.put(
            "/api/me/study-plan", headers=headers, json={**plan, "timezone": "Mars/Olympus"}
        )
    ).status_code == 422
    # Segunda local 00:00 = 03:00 UTC. Só 15s do primeiro intervalo pertencem à semana.
    body = await activity(
        client, session, headers, start=datetime(2026, 10, 12, 2, 59, 45, tzinfo=UTC)
    )
    for offset in [30000, 60000, 90000, 120000, 135000]:
        response = await client.post(
            "/api/me/activity/events",
            headers=headers,
            json=event(body["session_id"], offset, 15000 if offset == 135000 else 30000),
        )
        assert response.status_code == 200
    user_id = await session.scalar(select(User.id).where(User.email == "activity-week@example.com"))
    session.add(
        StudySessionProgress(
            user_id=user_id,
            lesson_id=body["lesson_id"],
            current_step="assistir",
            completed_steps=[],
            total_seconds=3600,
        )
    )
    await session.commit()
    today = (await client.get("/api/me/today", headers=headers)).json()
    assert today["recorded_minutes_this_week"] == 2
    assert today["recent_session"]["legacy_minutes"] == 60
    assert today["time_measurement"] == "active_intervals_v1"
    assert (await client.get("/api/me/today?course=voa-level-2", headers=headers)).json()[
        "recorded_minutes_this_week"
    ] == 0
