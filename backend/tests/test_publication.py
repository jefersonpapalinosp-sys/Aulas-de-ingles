"""40B.2b: real disposable PostgreSQL; public availability is not data ownership."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.db.models import (
    AssistReservation,
    Course,
    CourseUnit,
    Lesson,
    PracticeSessionItem,
    SpeakingAttempt,
    TranscriptionJob,
)
from tests.test_course_reviews import LEVEL_1_REVIEW_31_40_URL, attempt_body
from tests.test_media import position_body
from tests.test_practice import conta, create_body


@asynccontextmanager
async def unavailable(session, *, target="unit", state="archived"):
    course_id = await session.scalar(select(Course.id).where(Course.slug == "voa-level-1"))
    model = Course if target == "course" else CourseUnit
    condition = (
        Course.id == course_id
        if target == "course"
        else (CourseUnit.course_id == course_id) & (CourseUnit.slug == "31-40")
    )
    original = await session.scalar(select(model.status).where(condition))
    await session.execute(update(model).where(condition).values(status=state))
    await session.commit()
    try:
        yield
    finally:
        await session.rollback()
        await session.execute(update(model).where(condition).values(status=original))
        await session.commit()


@pytest.mark.parametrize("target", ["course", "unit"])
@pytest.mark.parametrize("state", ["planned", "archived"])
async def test_hidden_parents_block_slug_and_id_curricular_routes(client, session, target, state):
    headers = await conta(client, f"publication-{target}-{state}")
    lesson = (await client.get("/api/lessons/31")).json()
    lesson_id = await session.scalar(
        select(Lesson.id).join(Course).where(Course.slug == "voa-level-1", Lesson.number == 31)
    )
    exercise_id = lesson["exercises"][0]["id"]
    prompt_id = lesson["writing_prompts"][0]["id"]
    media = lesson["media"][0]
    review = (await client.get(LEVEL_1_REVIEW_31_40_URL, headers=headers)).json()
    async with unavailable(session, target=target, state=state):
        requests = [
            ("GET", "/api/lessons/31", None),
            ("GET", "/api/courses/voa-level-1/lessons/31", None),
            ("GET", "/api/courses/voa-level-1/lessons/31/exercises", None),
            ("GET", f"/api/exercises/{exercise_id}/hints/1", None),
            ("GET", f"/api/exercises/{exercise_id}/answer", None),
            (
                "POST",
                f"/api/exercises/{exercise_id}/attempt",
                {
                    "answer": "should",
                    "idempotency_key": str(uuid4()),
                },
            ),
            ("GET", f"/api/writing/prompts/{prompt_id}/draft", None),
            ("PUT", f"/api/writing/prompts/{prompt_id}/draft", {"text": "Private draft"}),
            ("POST", f"/api/writing/prompts/{prompt_id}/versions", {"text": "My version"}),
            ("POST", f"/api/writing/prompts/{prompt_id}/feedback", {"text": "I should go."}),
            ("GET", f"/api/media/{media['id']}/position", None),
            ("PUT", f"/api/media/{media['id']}/position", position_body(1)),
            (
                "POST",
                "/api/speaking/attempts",
                {
                    "cue_id": media["cues"][0]["id"],
                    "duration_ms": 1500,
                    "consent": True,
                },
            ),
            ("POST", f"/api/review/items/{lesson['vocab'][0]['id']}", None),
            ("POST", "/api/review/lessons/31", None),
            ("PUT", "/api/lessons/31/studied", None),
            (
                "POST",
                "/api/me/activity/sessions",
                {
                    "session_id": str(uuid4()),
                    "lesson_id": lesson_id,
                },
            ),
            ("POST", "/api/courses/voa-level-1/lessons/31/practice-sessions", create_body()),
            ("GET", LEVEL_1_REVIEW_31_40_URL, None),
            ("POST", f"{LEVEL_1_REVIEW_31_40_URL}/attempts", attempt_body(review, correct=False)),
            (
                "POST",
                "/api/me/notebook",
                {
                    "lesson_number": 31,
                    "kind": "note",
                    "content": "Private note",
                },
            ),
        ]
        for method, path, body in requests:
            response = await client.request(method, path, headers=headers, json=body)
            assert response.status_code == 404, (method, path, response.text)
            assert "x-aulas-offline" not in response.headers
        for path in ("/api/lessons", "/api/exercises?lesson=31", "/api/vocab?lesson=31"):
            response = await client.get(path)
            assert response.status_code == 200
            assert all(row.get("number") != 31 for row in response.json())
            if "lesson=31" in path:
                assert response.json() == []
        exported = (await client.get("/api/me/export", headers=headers)).json()
        assert exported["exercise_attempts"] == []
        assert exported["writing_feedback"] == []
        assert exported["practice_sessions"] == []
        assert exported["speaking"] == []


@pytest.mark.parametrize("target", ["course", "unit"])
async def test_archived_curriculum_hidden_without_hiding_other_courses(client, session, target):
    async with unavailable(session, target=target):
        courses = (await client.get("/api/courses")).json()
        if target == "course":
            assert "voa-level-1" not in {row["slug"] for row in courses}
            assert (await client.get("/api/courses/voa-level-1/curriculum")).status_code == 404
        else:
            assert courses[0]["published_lessons"] == 42
            curriculum = (await client.get("/api/courses/voa-level-1/curriculum")).json()
            assert "31-40" not in {unit["slug"] for unit in curriculum["units"]}
        assert (await client.get("/api/courses/voa-level-2/lessons/1")).status_code == 200
    assert (await client.get("/api/lessons/31")).status_code == 200


async def test_planned_course_retains_only_preview_not_published_counts(client, session):
    async with unavailable(session, target="course", state="planned"):
        courses = (await client.get("/api/courses")).json()
        assert courses[0]["published_lessons"] == 0
        curriculum = (await client.get("/api/courses/voa-level-1/curriculum")).json()
        assert curriculum["course"]["published_lessons"] == 0
        assert all(unit["published_lessons"] == 0 for unit in curriculum["units"])
        assert all(not unit["lessons"] and unit["review"] is None for unit in curriculum["units"])


async def test_archiving_preserves_owned_history_draft_media_export_and_copied_review(
    client, session, monkeypatch
):
    monkeypatch.setattr(get_settings(), "editorial_snapshots_enabled", True)
    headers = await conta(client, "archive-owner")
    other = await conta(client, "archive-other")
    lesson = (await client.get("/api/lessons/31")).json()
    prompt = lesson["writing_prompts"][0]["id"]
    exercise = lesson["exercises"][0]["id"]
    media = lesson["media"][0]
    draft_url = f"/api/writing/prompts/{prompt}/draft"
    draft = await client.put(draft_url, headers=headers, json={"text": "MY PRIVATE DRAFT"})
    assert draft.status_code == 200
    position_url = f"/api/media/{media['id']}/position"
    assert (
        await client.put(position_url, headers=headers, json=position_body(1))
    ).status_code == 200
    attempt = await client.post(
        f"/api/exercises/{exercise}/attempt",
        headers=headers,
        json={"answer": "should", "idempotency_key": str(uuid4())},
    )
    assert attempt.status_code == 200
    practice = await client.post(
        "/api/courses/voa-level-1/lessons/31/practice-sessions",
        headers=headers,
        json=create_body(mode="quick"),
    )
    assert practice.status_code == 201
    practice_id = practice.json()["id"]
    practice_item = await session.scalar(
        select(PracticeSessionItem.id).where(
            PracticeSessionItem.practice_session_id == practice_id,
            PracticeSessionItem.position == 0,
        )
    )
    speaking = await client.post(
        "/api/speaking/attempts",
        headers=headers,
        json={
            "cue_id": media["cues"][0]["id"],
            "duration_ms": 1500,
            "consent": True,
        },
    )
    assert speaking.status_code == 201
    assert (
        await client.post(
            f"/api/review/items/{lesson['vocab'][0]['id']}",
            headers=headers,
        )
    ).status_code == 200
    original_export = (await client.get("/api/me/export", headers=headers)).json()
    async with unavailable(session):
        assert (await client.get(draft_url, headers=headers)).json()["text"] == "MY PRIVATE DRAFT"
        assert (await client.get(draft_url, headers=other)).status_code == 404
        assert (await client.get(position_url, headers=headers)).json()["position_seconds"] == 1
        assert (await client.get(position_url, headers=other)).status_code == 404
        for kind, identifier in (
            ("exercise", attempt.json()["attempt_id"]),
            ("practice", practice_item),
            ("speaking", speaking.json()["id"]),
        ):
            path = f"/api/me/history/{kind}/{identifier}/content"
            response = await client.get(path, headers=headers)
            assert response.status_code == 200
            assert response.json()["status"] == "available"
            assert response.headers["cache-control"] == "private, no-store"
            assert (await client.get(path, headers=other)).status_code == 404
        assert (
            await client.get(f"/api/practice-sessions/{practice_id}", headers=headers)
        ).status_code == 200
        assert (
            await client.get(f"/api/practice-sessions/{practice_id}", headers=other)
        ).status_code == 404
        for suffix in (f"items/{exercise}/hints/1", f"items/{exercise}/reveal"):
            response = await client.post(
                f"/api/practice-sessions/{practice_id}/{suffix}", headers=headers
            )
            assert response.status_code == 404, response.text
        assert (
            await client.put(
                f"/api/practice-sessions/{practice_id}/position",
                headers=headers,
                json={
                    "current_position": 1,
                    "expected_revision": 1,
                    "idempotency_key": str(uuid4()),
                },
            )
        ).status_code == 404
        exported = (await client.get("/api/me/export", headers=headers)).json()
        for section in (
            "exercise_attempts",
            "writing",
            "practice_items",
            "speaking",
            "content_snapshots",
        ):
            assert exported[section] == original_export[section]
        clear = position_body(0, revision=1, completed=True)
        params = {key: clear[key] for key in ("expected_revision", "operation_key", "changed_at")}
        assert (await client.delete(position_url, headers=other, params=params)).status_code == 404
        assert (
            await client.delete(position_url, headers=headers, params=params)
        ).status_code == 204
        assert (await client.get(position_url, headers=headers)).json()["completed"]
        cards = (await client.get("/api/review/due", headers=headers)).json()
        assert cards
        card = cards[0]
        assert (
            await client.post(
                f"/api/review/{card['id']}/grade",
                headers=headers,
                json={
                    "quality": 4,
                    "expected_revision": card["revision"],
                    "idempotency_key": str(uuid4()),
                },
            )
        ).status_code == 200
        # A previously admitted personal upload can still be cancelled by its owner.
        assert (
            await client.delete(f"/api/speaking/attempts/{speaking.json()['id']}", headers=headers)
        ).status_code == 204


async def test_checkpoint_does_not_embed_media_from_archived_other_unit(client, session):
    headers = await conta(client, "cross-unit-media")
    path = "/api/courses/voa-level-1/units/40-44/review"
    assert (await client.get(path, headers=headers)).json()["listening_media"] is not None
    async with unavailable(session):
        response = await client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.json()["listening_media"] is None
        assert response.json()["listening_source_page_url"] is None


async def test_archive_blocks_new_transcription_without_spending_quota(
    client, session, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.invalid/stt")
    headers = await conta(client, "archive-stt")
    lesson = (await client.get("/api/lessons/31")).json()
    response = await client.post(
        "/api/speaking/attempts",
        headers=headers,
        json={
            "cue_id": lesson["media"][0]["cues"][0]["id"],
            "duration_ms": 1000,
            "consent": True,
        },
    )
    assert response.status_code == 201
    attempt_id = response.json()["id"]
    # Synthetic metadata only; no audio file or external provider is needed.
    await session.execute(
        update(SpeakingAttempt)
        .where(SpeakingAttempt.id == attempt_id)
        .values(
            status="ready",
            storage_key="synthetic-not-opened.webm",
        )
    )
    await session.commit()
    async with unavailable(session):
        response = await client.post(
            f"/api/speaking/attempts/{attempt_id}/transcription", headers=headers
        )
        assert response.status_code == 404, response.text
        assert await session.scalar(select(func.count()).select_from(AssistReservation)) == 0
        assert await session.scalar(select(func.count()).select_from(TranscriptionJob)) == 0
        history = (await client.get("/api/speaking/attempts", headers=headers)).json()
        assert [row["id"] for row in history] == [attempt_id]
