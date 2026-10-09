"""Painel Hoje, plano semanal, recomendações e competências."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Course,
    CourseReview,
    CourseReviewAttempt,
    CourseUnit,
    Lesson,
    LessonProgress,
    ReviewItem,
    StepProgress,
    StudySessionProgress,
    User,
)


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
    response = await client.get("/api/me/today", headers=headers)
    today = response.json()

    assert response.headers["cache-control"] == "private, no-store"
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
async def test_recommendation_offers_unit_checkpoint_after_required_lessons(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "today-checkpoint")
    user = (
        await session.execute(select(User).where(User.email == "today-checkpoint@example.com"))
    ).scalar_one()
    lessons = list(
        (
            await session.execute(select(Lesson).where(Lesson.number.in_([40, 41, 42, 43, 44])))
        ).scalars()
    )
    session.add_all([LessonProgress(user_id=user.id, lesson_id=lesson.id) for lesson in lessons])
    await session.commit()

    recommendation = (await client.get("/api/me/today", headers=headers)).json()["recommendation"]
    assert recommendation["kind"] == "course_review"
    assert recommendation["title"] == "Checkpoint 40–44 · Level 1"
    assert recommendation["href"] == ("/cursos/voa-level-1/unidades/40-44/checkpoint")

    detail = (
        await client.get("/api/courses/voa-level-1/units/40-44/review", headers=headers)
    ).json()
    submitted = await client.post(
        "/api/courses/voa-level-1/units/40-44/review/attempts",
        headers=headers,
        json={
            "idempotency_key": str(uuid4()),
            "content_version": detail["content_version"],
            "answers": [
                {
                    "question_id": question["id"],
                    "answer": question["options"][0],
                }
                for question in detail["questions"]
            ],
        },
    )
    assert submitted.status_code == 201
    after_attempt = (await client.get("/api/me/today", headers=headers)).json()["recommendation"]
    assert after_attempt["kind"] != "course_review"

    review = (
        await session.execute(
            select(CourseReview)
            .join(CourseUnit, CourseReview.unit_id == CourseUnit.id)
            .where(CourseUnit.slug == "40-44")
        )
    ).scalar_one()
    original_version = review.content_version
    try:
        review.content_version = original_version + 1
        await session.commit()
        after_update = (await client.get("/api/me/today", headers=headers)).json()["recommendation"]
        assert after_update["kind"] == "course_review"
    finally:
        review.content_version = original_version
        await session.commit()


@pytest.mark.asyncio
async def test_today_isolates_reviews_sessions_and_time_by_course(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "today-multi-course")
    level_1 = (
        await session.execute(select(Course).where(Course.slug == "voa-level-1"))
    ).scalar_one()
    level_2 = (
        await session.execute(select(Course).where(Course.slug == "voa-level-2"))
    ).scalar_one()
    level_2_unit = (
        await session.execute(
            select(CourseUnit).where(
                CourseUnit.course_id == level_2.id,
                CourseUnit.slug == "1-5",
            )
        )
    ).scalar_one()
    original_course_status = level_2.status
    original_unit_status = level_2_unit.status
    created_lesson_id: int | None = None

    try:
        level_2.status = "planned"
        await session.commit()
        unavailable = await client.get("/api/me/today?course=voa-level-2", headers=headers)
        assert unavailable.status_code == 404

        level_2.status = "published"
        level_2_unit.status = "published"
        level_2_lesson = (
            await session.execute(
                select(Lesson).where(
                    Lesson.course_id == level_2.id,
                    Lesson.number == 1,
                )
            )
        ).scalar_one_or_none()
        if level_2_lesson is None:
            level_2_lesson = Lesson(
                course_id=level_2.id,
                unit_id=level_2_unit.id,
                number=1,
                slug="dashboard-level-2-lesson-1",
                position=1,
                title="Budget Cuts",
                title_pt="Cortes no orçamento",
                voa_url="https://example.com/level-2/lesson-1",
                grammar_tag="Present perfect",
                focus_points=[],
                lead="Fixture de isolamento do painel Hoje.",
                warmup_prompt="What changed?",
                listening_focus="Identifique a mudança principal.",
            )
            session.add(level_2_lesson)
            await session.flush()
            created_lesson_id = level_2_lesson.id

        await session.commit()
        empty_level_1 = (await client.get("/api/me/today", headers=headers)).json()
        empty_level_2 = (
            await client.get("/api/me/today?course=voa-level-2", headers=headers)
        ).json()
        assert empty_level_1["recommendation"]["lesson_number"] == 31
        assert empty_level_1["recommendation"]["course_slug"] == "voa-level-1"
        assert empty_level_2["recommendation"]["lesson_number"] == 1
        assert empty_level_2["recommendation"]["course_slug"] == "voa-level-2"
        assert empty_level_2["recommendation"]["href"].startswith("/cursos/voa-level-2/aulas/1/")

        user = (
            await session.execute(
                select(User).where(User.email == "today-multi-course@example.com")
            )
        ).scalar_one()
        level_1_lesson = (
            await session.execute(
                select(Lesson).where(
                    Lesson.course_id == level_1.id,
                    Lesson.number == 31,
                )
            )
        ).scalar_one()
        now = datetime.now(UTC)
        level_1_session = StudySessionProgress(
            user_id=user.id,
            lesson_id=level_1_lesson.id,
            current_step="assistir",
            completed_steps=["preparar"],
            total_seconds=120,
            updated_at=now - timedelta(minutes=2),
        )
        level_2_session = StudySessionProgress(
            user_id=user.id,
            lesson_id=level_2_lesson.id,
            current_step="estudar",
            completed_steps=["preparar", "assistir"],
            total_seconds=300,
            updated_at=now - timedelta(minutes=1),
        )
        cards = [
            ReviewItem(
                user_id=user.id,
                lesson_id=lesson.id,
                item_type="listening",
                source_type="dashboard_test",
                source_id=key,
                source_key=f"dashboard-test:{key}",
                skill="listening",
                prompt=f"Prompt {key}",
                answer=f"Answer {key}",
                origin_reason="Fixture de isolamento entre cursos.",
                estimated_seconds=60,
                status="active",
                due_at=now - timedelta(minutes=1),
            )
            for key, lesson in (
                (101, level_1_lesson),
                (201, level_2_lesson),
                (202, level_2_lesson),
            )
        ]
        session.add_all([level_1_session, level_2_session, *cards])
        await session.commit()

        default_today = (await client.get("/api/me/today", headers=headers)).json()
        level_2_today = (
            await client.get("/api/me/today?course=voa-level-2", headers=headers)
        ).json()

        assert default_today["recommendation"] == {
            "kind": "review",
            "title": "Revisar 1 item",
            "reason": "Esses itens já venceram no seu ciclo de revisão espaçada.",
            "href": "/revisar?course=voa-level-1",
            "estimated_minutes": 5,
            "course_slug": "voa-level-1",
            "lesson_number": None,
        }
        assert default_today["recorded_minutes_this_week"] == 2
        assert default_today["recent_session"]["course_slug"] == "voa-level-1"
        assert default_today["recent_session"]["lesson_number"] == 31

        assert level_2_today["recommendation"]["title"] == "Revisar 2 itens"
        assert level_2_today["recommendation"]["href"] == ("/revisar?course=voa-level-2")
        assert level_2_today["recommendation"]["course_slug"] == "voa-level-2"
        assert level_2_today["recorded_minutes_this_week"] == 5
        assert level_2_today["recent_session"]["course_slug"] == "voa-level-2"
        assert level_2_today["recent_session"]["lesson_number"] == 1

        for card in cards:
            card.status = "suspended"
        await session.commit()

        level_1_resume = (await client.get("/api/me/today", headers=headers)).json()[
            "recommendation"
        ]
        level_2_resume = (
            await client.get("/api/me/today?course=voa-level-2", headers=headers)
        ).json()["recommendation"]
        assert level_1_resume["title"] == "Continuar a Aula 31"
        assert level_1_resume["course_slug"] == "voa-level-1"
        assert level_1_resume["href"].endswith("/31/estudar/assistir")
        assert level_2_resume["title"] == "Continuar a Aula 1"
        assert level_2_resume["course_slug"] == "voa-level-2"
        assert level_2_resume["href"].endswith("/1/estudar/estudar")

        level_2_session.current_step = "revisar"
        level_2_session.completed_steps = [
            "preparar",
            "assistir",
            "estudar",
            "praticar",
            "revisar",
        ]
        published_lessons = list(
            (
                await session.execute(
                    select(Lesson)
                    .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
                    .where(
                        Lesson.course_id == level_2.id,
                        CourseUnit.status == "published",
                    )
                )
            ).scalars()
        )
        assert len(published_lessons) == 30
        session.add_all(
            [LessonProgress(user_id=user.id, lesson_id=lesson.id) for lesson in published_lessons]
        )
        published_reviews = list(
            (
                await session.execute(
                    select(CourseReview)
                    .join(CourseUnit, CourseReview.unit_id == CourseUnit.id)
                    .where(
                        CourseUnit.course_id == level_2.id,
                        CourseUnit.status == "published",
                        CourseReview.status == "published",
                    )
                )
            ).scalars()
        )
        assert len(published_reviews) == 6
        await session.commit()

        if published_reviews:
            checkpoint = (
                await client.get("/api/me/today?course=voa-level-2", headers=headers)
            ).json()["recommendation"]
            assert checkpoint["kind"] == "course_review"
            assert checkpoint["title"].endswith("· Level 2")
            assert checkpoint["course_slug"] == "voa-level-2"
            session.add_all(
                [
                    CourseReviewAttempt(
                        user_id=user.id,
                        review_id=review.id,
                        idempotency_key=str(uuid4()),
                        request_hash="0" * 64,
                        content_version=review.content_version,
                        answers=[],
                        result=[],
                        score=1,
                        total=1,
                    )
                    for review in published_reviews
                ]
            )
            await session.commit()

        notebook = (await client.get("/api/me/today?course=voa-level-2", headers=headers)).json()[
            "recommendation"
        ]
        assert notebook["kind"] == "practice"
        assert notebook["href"] == "/caderno?course=voa-level-2"
        assert notebook["course_slug"] == "voa-level-2"
    finally:
        await session.rollback()
        if created_lesson_id is not None:
            await session.execute(delete(Lesson).where(Lesson.id == created_lesson_id))
        level_2.status = original_course_status
        level_2_unit.status = original_unit_status
        await session.commit()


@pytest.mark.asyncio
async def test_today_ignora_retomada_de_unidade_nao_publicada(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "today-planned-resume")
    user = (
        await session.execute(select(User).where(User.email == "today-planned-resume@example.com"))
    ).scalar_one()
    course = (
        await session.execute(select(Course).where(Course.slug == "voa-level-2"))
    ).scalar_one()
    planned_unit = (
        await session.execute(
            select(CourseUnit).where(
                CourseUnit.course_id == course.id,
                CourseUnit.slug == "26-30",
            )
        )
    ).scalar_one()
    assert course.status == "published"
    # Sprint 30: o Level 2 fechou e não há mais unidade planejada no seed.
    # A regra continua valendo, então o teste cria a sua.
    planned_unit = CourseUnit(
        course_id=course.id,
        slug="31-35",
        title="Aulas 31–35",
        position=7,
        status="planned",
        lesson_start=31,
        lesson_end=35,
        total_lessons=5,
    )
    session.add(planned_unit)
    await session.flush()
    assert planned_unit.status == "planned"

    hidden_lesson = Lesson(
        course_id=course.id,
        unit_id=planned_unit.id,
        number=31,
        slug="dashboard-hidden-level-2-lesson-16",
        position=1,
        title="Find Your Joy!",
        title_pt="Encontre sua alegria!",
        voa_url="https://example.com/level-2/lesson-16",
        grammar_tag="Fixture planned",
        focus_points=[],
        lead="Fixture de retomada não publicada.",
        warmup_prompt="What happened?",
        listening_focus="Identifique a notícia principal.",
    )
    session.add(hidden_lesson)
    await session.flush()
    now = datetime.now(UTC)
    session.add_all(
        [
            StudySessionProgress(
                user_id=user.id,
                lesson_id=hidden_lesson.id,
                current_step="assistir",
                completed_steps=["preparar"],
                total_seconds=600,
                updated_at=now,
            ),
            ReviewItem(
                user_id=user.id,
                lesson_id=hidden_lesson.id,
                item_type="listening",
                source_type="dashboard_test",
                source_id=616,
                source_key="dashboard-test:hidden-planned-616",
                skill="listening",
                prompt="Hidden planned prompt",
                answer="Hidden planned answer",
                origin_reason="Fixture em unidade não publicada.",
                estimated_seconds=60,
                status="active",
                due_at=now - timedelta(minutes=1),
            ),
        ]
    )
    await session.commit()

    try:
        response = await client.get("/api/me/today?course=voa-level-2", headers=headers)
        today = response.json()
        assert response.headers["cache-control"] == "private, no-store"
        assert today["recommendation"]["kind"] == "start_lesson"
        assert today["recommendation"]["lesson_number"] == 1
        assert today["recent_session"] is None
        assert today["recorded_minutes_this_week"] == 0
    finally:
        await session.execute(delete(Lesson).where(Lesson.id == hidden_lesson.id))
        await session.execute(delete(CourseUnit).where(CourseUnit.id == planned_unit.id))
        await session.commit()


@pytest.mark.asyncio
async def test_skill_percentage_requires_three_evidences(client: AsyncClient) -> None:
    headers = await conta(client, "today-skill")
    exercise = (await client.get("/api/exercises?lesson=31")).json()[0]

    empty_response = await client.get("/api/me/skills", headers=headers)
    empty = empty_response.json()
    assert empty_response.headers["cache-control"] == "private, no-store"
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
async def test_skills_sao_isoladas_por_curso_e_unidade(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "skills-por-unidade")
    lesson_31 = (await client.get("/api/exercises?lesson=31")).json()
    lesson_41 = (await client.get("/api/exercises?lesson=41")).json()
    exercise_31 = next(item for item in lesson_31 if item["skill"] == "grammar")
    exercise_41 = next(item for item in lesson_41 if item["skill"] == "grammar")

    for key in (701, 702):
        response = await client.post(
            f"/api/exercises/{exercise_31['id']}/attempt",
            headers=headers,
            json=attempt("definitely wrong", key),
        )
        assert response.status_code == 200
        assert response.json()["correct"] is False
    response = await client.post(
        f"/api/exercises/{exercise_41['id']}/attempt",
        headers=headers,
        json=attempt("definitely wrong", 703),
    )
    assert response.status_code == 200
    assert response.json()["correct"] is False

    first = (
        await client.get("/api/me/skills?course=voa-level-1&unit=31-40", headers=headers)
    ).json()
    second = (
        await client.get("/api/me/skills?course=voa-level-1&unit=40-44", headers=headers)
    ).json()
    future = (
        await client.get("/api/me/skills?course=voa-level-1&unit=45-49", headers=headers)
    ).json()
    other_course = (
        await client.get("/api/me/skills?course=voa-level-2&unit=31-40", headers=headers)
    ).json()
    global_skills = (await client.get("/api/me/skills", headers=headers)).json()

    first_grammar = next(item for item in first if item["skill"] == "grammar")
    second_grammar = next(item for item in second if item["skill"] == "grammar")
    future_grammar = next(item for item in future if item["skill"] == "grammar")
    other_grammar = next(item for item in other_course if item["skill"] == "grammar")
    global_grammar = next(item for item in global_skills if item["skill"] == "grammar")

    assert first_grammar["samples"] == 2
    assert first_grammar["score_percent"] is None
    assert "Comparativos + conselho" in first_grammar["fragile_topics"]
    assert second_grammar["samples"] == 1
    assert second_grammar["fragile_topics"] == []
    assert future_grammar["samples"] == 0
    assert other_grammar["samples"] == 0
    assert global_grammar["samples"] == 3
    assert global_grammar["score_percent"] == 0
    assert global_grammar["status"] == "developing"

    ambiguous = await client.get("/api/me/skills?unit=31-40", headers=headers)
    assert ambiguous.status_code == 422

    course = (
        await session.execute(select(Course).where(Course.slug == "voa-level-1"))
    ).scalar_one()
    unit = (
        await session.execute(
            select(CourseUnit).where(
                CourseUnit.course_id == course.id,
                CourseUnit.slug == "31-40",
            )
        )
    ).scalar_one()
    original_course_status = course.status
    original_unit_status = unit.status
    try:
        unit.status = "planned"
        await session.commit()
        published_only = (
            await client.get("/api/me/skills?course=voa-level-1", headers=headers)
        ).json()
        hidden_unit = (
            await client.get(
                "/api/me/skills?course=voa-level-1&unit=31-40",
                headers=headers,
            )
        ).json()
        assert next(item for item in published_only if item["skill"] == "grammar")["samples"] == 1
        hidden_grammar = next(item for item in hidden_unit if item["skill"] == "grammar")
        assert hidden_grammar["samples"] == 0
        assert hidden_grammar["score_percent"] is None
        assert hidden_grammar["fragile_topics"] == []

        unit.status = "published"
        course.status = "planned"
        await session.commit()
        hidden_course = (
            await client.get("/api/me/skills?course=voa-level-1", headers=headers)
        ).json()
        assert all(item["samples"] == 0 for item in hidden_course)
    finally:
        course.status = original_course_status
        unit.status = original_unit_status
        await session.commit()


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
