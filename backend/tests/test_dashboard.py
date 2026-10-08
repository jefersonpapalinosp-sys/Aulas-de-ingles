"""Painel Hoje, plano semanal, recomendações e competências."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StepProgress, StudySessionProgress, User


async def conta(client: AsyncClient, suffix: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"{suffix}@example.com",
            "password": "senha-bem-grande",
            "display_name": suffix,
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def attempt(answer: str, key: int) -> dict[str, str]:
    return {
        "answer": answer,
        "idempotency_key": f"10000000-0000-4000-8000-{key:012d}",
    }


@pytest.mark.asyncio
async def test_dashboard_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/me/today")).status_code == 401
    assert (await client.get("/api/me/skills")).status_code == 401
    assert (await client.get("/api/me/study-plan")).status_code == 401


@pytest.mark.asyncio
async def test_today_explains_first_recommendation_and_has_safe_defaults(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "today-default")
    today = (await client.get("/api/me/today", headers=headers)).json()

    assert today["recommendation"]["kind"] == "start_lesson"
    assert today["recommendation"]["course_slug"] == "voa-level-1"
    assert today["recommendation"]["lesson_number"] == 31
    assert today["recommendation"]["href"] == "/cursos/voa-level-1/aulas/31/estudar"
    assert today["recommendation"]["reason"]
    assert today["plan"] == {
        "weekly_minutes": 90,
        "preferred_days": ["mon", "wed", "fri"],
        "goal": "Criar constância no inglês",
        "updated_at": None,
    }
    assert today["recent_session"] is None


@pytest.mark.asyncio
async def test_plan_is_editable_normalized_and_validated(client: AsyncClient) -> None:
    headers = await conta(client, "today-plan")
    body = {
        "weekly_minutes": 150,
        "preferred_days": ["fri", "mon", "wed"],
        "goal": "Conversar com confiança",
    }
    saved = await client.put("/api/me/study-plan", headers=headers, json=body)
    repeated = await client.put(
        "/api/me/study-plan",
        headers=headers,
        json={**body, "preferred_days": ["mon", "mon"]},
    )
    fetched = await client.get("/api/me/study-plan", headers=headers)

    assert saved.status_code == 200
    assert saved.json()["preferred_days"] == ["mon", "wed", "fri"]
    assert fetched.json()["weekly_minutes"] == 150
    assert repeated.status_code == 422


@pytest.mark.asyncio
async def test_recommendation_prioritizes_due_review_then_resume(client: AsyncClient) -> None:
    headers = await conta(client, "today-order")
    await client.put(
        "/api/lessons/31/study-session",
        headers=headers,
        json={"current_step": "assistir", "completed_steps": ["preparar"]},
    )
    resumed = (await client.get("/api/me/today", headers=headers)).json()["recommendation"]
    assert resumed["kind"] == "continue_lesson"
    assert resumed["course_slug"] == "voa-level-1"
    assert resumed["href"].startswith("/cursos/voa-level-1/aulas/31/estudar/")
    assert resumed["href"].endswith("/assistir")
    assert "parou" in resumed["reason"].lower()

    await client.put("/api/lessons/31/studied", headers=headers)
    review = (await client.get("/api/me/today", headers=headers)).json()["recommendation"]
    assert review["kind"] == "review"
    assert "venceram" in review["reason"].lower()


@pytest.mark.asyncio
async def test_skill_percentage_requires_three_evidences(client: AsyncClient) -> None:
    headers = await conta(client, "today-skill")
    exercise = (await client.get("/api/exercises?lesson=31")).json()[0]

    empty = (await client.get("/api/me/skills", headers=headers)).json()
    grammar = next(item for item in empty if item["skill"] == "grammar")
    assert grammar["samples"] == 0
    assert grammar["score_percent"] is None

    await client.post(
        f"/api/exercises/{exercise['id']}/attempt",
        headers=headers,
        json=attempt("faster", 1),
    )
    await client.post(
        f"/api/exercises/{exercise['id']}/attempt",
        headers=headers,
        json=attempt("more fast", 2),
    )
    two = (await client.get("/api/me/skills", headers=headers)).json()
    grammar = next(item for item in two if item["skill"] == "grammar")
    assert grammar["samples"] == 2
    assert grammar["score_percent"] is None
    assert grammar["fragile_topics"]

    await client.post(
        f"/api/exercises/{exercise['id']}/attempt",
        headers=headers,
        json=attempt("faster", 3),
    )
    three = (await client.get("/api/me/skills", headers=headers)).json()
    grammar = next(item for item in three if item["skill"] == "grammar")
    assert grammar["samples"] == 3
    assert grammar["score_percent"] == 67
    assert grammar["status"] == "steady"


@pytest.mark.asyncio
async def test_session_records_time_steps_and_completion(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "today-time")
    await client.put(
        "/api/lessons/31/study-session",
        headers=headers,
        json={"current_step": "preparar", "completed_steps": []},
    )
    user = (
        await session.execute(select(User).where(User.email == "today-time@example.com"))
    ).scalar_one()
    study = (
        await session.execute(
            select(StudySessionProgress).where(StudySessionProgress.user_id == user.id)
        )
    ).scalar_one()
    study.updated_at = datetime.now(UTC) - timedelta(seconds=125)
    await session.commit()

    completed = await client.put(
        "/api/lessons/31/study-session",
        headers=headers,
        json={
            "current_step": "revisar",
            "completed_steps": ["preparar", "assistir", "estudar", "praticar", "revisar"],
        },
    )
    assert completed.json()["total_seconds"] >= 124
    assert completed.json()["completed_at"] is not None

    step_count = len(
        list(
            (
                await session.execute(
                    select(StepProgress).where(StepProgress.study_session_id == study.id)
                )
            ).scalars()
        )
    )
    assert step_count == 5
    today = (await client.get("/api/me/today", headers=headers)).json()
    assert today["recorded_minutes_this_week"] == 2
    assert today["recent_session"]["completed_steps"] == 5
    assert today["recent_session"]["course_slug"] == "voa-level-1"


@pytest.mark.asyncio
async def test_plans_and_skills_are_isolated_by_account(client: AsyncClient) -> None:
    ana = await conta(client, "today-ana")
    bruno = await conta(client, "today-bruno")
    await client.put(
        "/api/me/study-plan",
        headers=ana,
        json={"weekly_minutes": 210, "preferred_days": ["sat"], "goal": "Viagem"},
    )

    ana_plan = (await client.get("/api/me/study-plan", headers=ana)).json()
    bruno_plan = (await client.get("/api/me/study-plan", headers=bruno)).json()
    assert ana_plan["weekly_minutes"] == 210
    assert bruno_plan["weekly_minutes"] == 90
