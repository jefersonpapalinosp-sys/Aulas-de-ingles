"""40B.2a: private snapshots in real disposable PostgreSQL, no provider calls."""

import asyncio
import hashlib
import json
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.db import editorial_identity
from app.db.models import (
    CourseReviewQuestion,
    EvidenceContentSnapshot,
    Exercise,
    ExerciseAnswer,
    ExerciseAttempt,
    LessonMedia,
    PracticeSessionItem,
    TranscriptCue,
    User,
    WritingPrompt,
)
from app.services import editorial_history
from tests.test_course_reviews import REVIEW_URL, attempt_body
from tests.test_practice import conta, create_body


@pytest.fixture(autouse=True)
def capture_enabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "editorial_snapshots_enabled", True)


def history(kind, identifier):
    return f"/api/me/history/{kind}/{identifier}/content"


async def exercise_attempt(client, headers):
    lesson = (await client.get("/api/lessons/31")).json()
    exercise = lesson["exercises"][0]
    path = f"/api/exercises/{exercise['id']}/attempt"
    body = {"answer": "should", "idempotency_key": str(uuid4())}
    response = await client.post(path, headers=headers, json=body)
    assert response.status_code == 200, response.text
    return path, body, response.json(), lesson


async def test_all_modalities_private_export_and_flag_disable_preserves_read(
    client, session, monkeypatch
):
    headers = await conta(client, "snapshots")
    _, _, attempt, lesson = await exercise_attempt(client, headers)
    practice = await client.post(
        "/api/courses/voa-level-1/lessons/31/practice-sessions",
        headers=headers,
        json=create_body(mode="quick"),
    )
    assert practice.status_code == 201
    assert all(
        item["historical_content_status"] == "available" for item in practice.json()["items"]
    )
    practice_item = await session.scalar(
        select(PracticeSessionItem.id).where(
            PracticeSessionItem.practice_session_id == practice.json()["id"],
            PracticeSessionItem.position == 0,
        )
    )
    prompt_id = lesson["writing_prompts"][0]["id"]
    writing = await client.post(
        f"/api/writing/prompts/{prompt_id}/feedback",
        headers=headers,
        json={"text": "My train is faster than a bus. You should try it."},
    )
    assert writing.status_code == 200
    assert writing.json()["historical_content_status"] == "available"
    cue_id = lesson["media"][0]["cues"][0]["id"]
    speaking = await client.post(
        "/api/speaking/attempts",
        headers=headers,
        json={"cue_id": cue_id, "duration_ms": 1500, "consent": True},
    )
    assert speaking.status_code == 201, speaking.text
    assert speaking.json()["historical_content_status"] == "available"
    assert speaking.json()["cue_text"] == lesson["media"][0]["cues"][0]["text_en"]
    review = (await client.get(REVIEW_URL, headers=headers)).json()
    checkpoint = await client.post(
        f"{REVIEW_URL}/attempts", headers=headers, json=attempt_body(review)
    )
    assert checkpoint.status_code == 201
    targets = [
        ("exercise", attempt["attempt_id"]),
        ("practice", practice_item),
        ("writing", writing.json()["id"]),
        ("speaking", speaking.json()["id"]),
        ("checkpoint", checkpoint.json()["id"]),
    ]
    other = await conta(client, "snapshot-other")
    first_page = await client.get("/api/me/history/page", headers=headers, params={"limit": 2})
    assert first_page.status_code == 200
    assert first_page.headers["cache-control"] == "private, no-store"
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["next_cursor"]
    pages = [first_page.json()]
    while pages[-1]["next_cursor"]:
        response = await client.get(
            "/api/me/history/page",
            headers=headers,
            params={"limit": 2, "cursor": pages[-1]["next_cursor"]},
        )
        assert response.status_code == 200, response.text
        pages.append(response.json())
    listed = [item for page in pages for item in page["items"]]
    assert len(listed) == 9
    assert len({(item["evidence_kind"], item["evidence_id"]) for item in listed}) == 9
    assert {item["evidence_kind"] for item in listed} == {
        "exercise",
        "practice",
        "writing",
        "speaking",
        "checkpoint",
    }
    assert all(item["schema_version"] == "1.0" for item in listed)
    assert (await client.get("/api/me/history/page", headers=other)).json() == {
        "items": [],
        "next_cursor": None,
    }
    for kind, identifier in targets:
        response = await client.get(history(kind, identifier), headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "available"
        assert response.json()["schema_version"] == "1.0"
        content = response.json()["content"]
        assert content["editorial_identity_contract"] == "explicit_uuid_v1"
        if kind == "checkpoint":
            for question in content["questions"]:
                assert question["editorial_key"] == await session.scalar(
                    select(CourseReviewQuestion.editorial_key).where(
                        CourseReviewQuestion.id == question["id"]
                    )
                )
        else:
            model = {
                "exercise": Exercise,
                "practice": Exercise,
                "writing": WritingPrompt,
                "speaking": TranscriptCue,
            }[kind]
            assert content["editorial_key"] == await session.scalar(
                select(model.editorial_key).where(model.id == content["source_id"])
            )
            if kind == "speaking":
                assert content["media"]["editorial_key"] == await session.scalar(
                    select(LessonMedia.editorial_key).where(LessonMedia.id == content["media_id"])
                )
        assert response.headers["cache-control"] == "private, no-store"
        assert "x-aulas-offline" not in response.headers
        assert (await client.get(history(kind, identifier), headers=other)).status_code == 404
    pending = (await client.get(history("practice", practice_item), headers=headers)).json()
    assert pending["content_sha256"] is None
    assert pending["content"]["correction_hidden"]
    assert not {"answers", "hints", "explanation"} & pending["content"].keys()
    monkeypatch.setattr(get_settings(), "editorial_snapshots_enabled", False)
    exported = (await client.get("/api/me/export", headers=headers)).json()
    assert len(exported["content_snapshots"]) == 9  # 5 practice items + 4 events
    assert exported["scope"]["row_counts"]["evidence_content_snapshot"] == 9
    assert exported["exercise_attempts"][0]["historical_content_status"] == "available"
    assert exported["content_snapshots"]
    for row in exported["content_snapshots"]:
        canonical = json.dumps(
            row["content"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        assert hashlib.sha256(canonical.encode()).hexdigest() == row["content_sha256"]
    assert (await client.get("/api/me/export", headers=other)).json()["content_snapshots"] == []
    assert (await client.get(history("writing", writing.json()["id"]), headers=headers)).json()[
        "status"
    ] == "available"


async def test_history_and_idempotent_feedback_survive_changed_answer(client, session):
    headers = await conta(client, "snapshot-edit")
    path, body, original, lesson = await exercise_attempt(client, headers)
    identifier = original["attempt_id"]
    before = (await client.get(history("exercise", identifier), headers=headers)).json()
    exercise_id = lesson["exercises"][0]["id"]
    table = Exercise.__table__
    old = (await session.execute(select(table).where(table.c.id == exercise_id))).mappings().one()
    answers = list(
        (
            await session.execute(
                select(ExerciseAnswer.__table__).where(ExerciseAnswer.exercise_id == exercise_id)
            )
        ).mappings()
    )
    await session.execute(
        update(Exercise)
        .where(Exercise.id == exercise_id)
        .values(
            prompt="CURRENT CONTENT MUST NOT REPLACE HISTORY", explanation="Changed explanation"
        )
    )
    await session.execute(
        update(ExerciseAnswer)
        .where(ExerciseAnswer.exercise_id == exercise_id)
        .values(value="changed answer")
    )
    await session.commit()
    try:
        assert (await client.get(history("exercise", identifier), headers=headers)).json() == before
        replay = await client.post(path, headers=headers, json=body)
        assert replay.status_code == 200
        assert replay.json() == original
        assert await session.scalar(select(func.count()).select_from(EvidenceContentSnapshot)) == 1
    finally:
        await session.rollback()
        await session.execute(
            update(Exercise)
            .where(Exercise.id == exercise_id)
            .values(prompt=old["prompt"], explanation=old["explanation"])
        )
        for answer in answers:
            await session.execute(
                update(ExerciseAnswer)
                .where(ExerciseAnswer.id == answer["id"])
                .values(value=answer["value"])
            )
        await session.commit()


async def test_legacy_absence_is_not_backfilled_on_retry(client, session, monkeypatch):
    headers = await conta(client, "snapshot-legacy")
    monkeypatch.setattr(get_settings(), "editorial_snapshots_enabled", False)
    path, body, result, _ = await exercise_attempt(client, headers)
    monkeypatch.setattr(get_settings(), "editorial_snapshots_enabled", True)
    assert (await client.post(path, headers=headers, json=body)).status_code == 200
    data = (await client.get(history("exercise", result["attempt_id"]), headers=headers)).json()
    assert data["status"] == "unavailable" and data["content"] is None
    assert await session.scalar(select(func.count()).select_from(EvidenceContentSnapshot)) == 0


async def test_immutable_owner_fk_and_unique_constraints(client, session):
    headers = await conta(client, "snapshot-owner")
    _, _, result, _ = await exercise_attempt(client, headers)
    other = User(
        email="snapshot-other@example.test", display_name="Other", password_hash="synthetic"
    )
    session.add(other)
    await session.commit()
    snapshot = (await session.execute(select(EvidenceContentSnapshot.__table__))).mappings().one()
    row = dict(snapshot)
    row.pop("id")
    for statement in (
        update(EvidenceContentSnapshot).values(content={"tampered": True}),
        update(EvidenceContentSnapshot).values(user_id=other.id),
        insert(EvidenceContentSnapshot).values(**dict(row, user_id=other.id)),
        insert(EvidenceContentSnapshot).values(**row),
        insert(EvidenceContentSnapshot).values(**dict(row, exercise_attempt_id=None)),
    ):
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(statement)
    await session.execute(delete(ExerciseAttempt).where(ExerciseAttempt.id == result["attempt_id"]))
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(EvidenceContentSnapshot)) == 0


async def test_capture_failure_rolls_back_event_and_skills(client, session, monkeypatch):
    headers = await conta(client, "snapshot-rollback")
    lesson = (await client.get("/api/lessons/31")).json()

    async def oversized(*args, **kwargs):
        raise editorial_history.HTTPException(413, "synthetic too large")

    monkeypatch.setattr(editorial_history, "capture", oversized)
    response = await client.post(
        f"/api/exercises/{lesson['exercises'][0]['id']}/attempt",
        headers=headers,
        json={"answer": "anything", "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 413
    assert await session.scalar(select(func.count()).select_from(ExerciseAttempt)) == 0
    assert await session.scalar(select(func.count()).select_from(EvidenceContentSnapshot)) == 0


async def test_snapshot_lookup_requires_auth_and_valid_kind(client):
    assert (await client.get(history("exercise", 1))).status_code == 401
    assert (await client.get("/api/me/history/page")).status_code == 401
    headers = await conta(client, "snapshot-route")
    assert (await client.get(history("exercise", 99999999), headers=headers)).status_code == 404
    assert (await client.get(history("unknown", 1), headers=headers)).status_code == 422
    assert (await client.get(history("exercise", 0), headers=headers)).status_code == 422
    invalid = await client.get(
        "/api/me/history/page", headers=headers, params={"cursor": "not-a-cursor"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_cursor"


async def test_read_handles_unmigrated_schema_without_capture(client, monkeypatch):
    headers = await conta(client, "snapshot-no-schema")
    monkeypatch.setattr(get_settings(), "editorial_snapshots_enabled", False)
    _, _, result, _ = await exercise_attempt(client, headers)

    async def absent(session):
        return False

    monkeypatch.setattr(editorial_history, "schema_available", absent)
    response = await client.get(history("exercise", result["attempt_id"]), headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "unavailable"
    page = await client.get("/api/me/history/page", headers=headers)
    assert page.status_code == 200 and page.json() == {"items": [], "next_cursor": None}


async def test_limit_refuses_oversized_snapshot_before_insert(session):
    with pytest.raises(editorial_history.HTTPException) as error:
        await editorial_history.capture(session, "exercise", 1, 1, {"text": "x" * 200001})
    assert error.value.status_code == 413


async def test_snapshot_without_identity_migration_is_not_fabricated_or_upgraded(
    client, monkeypatch
):
    headers = await conta(client, "snapshot-before-identity")
    original = editorial_identity.schema_available

    async def absent(session):
        return False

    monkeypatch.setattr(editorial_identity, "schema_available", absent)
    path, body, result, _ = await exercise_attempt(client, headers)
    before = (await client.get(history("exercise", result["attempt_id"]), headers=headers)).json()
    assert before["schema_version"] == "1.0"
    assert "editorial_key" not in before["content"]
    monkeypatch.setattr(editorial_identity, "schema_available", original)
    assert (await client.post(path, headers=headers, json=body)).json() == result
    assert (
        await client.get(history("exercise", result["attempt_id"]), headers=headers)
    ).json() == before


async def test_snapshot_table_is_empty_for_preexisting_feedback(session):
    # Migration does not copy present-day prompts into old events.
    assert await session.scalar(select(func.count()).select_from(EvidenceContentSnapshot)) == 0
    assert (
        await session.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar_one() == "f40c2d9a1b73"


async def test_enabled_without_schema_fails_closed(client, session, monkeypatch):
    headers = await conta(client, "snapshot-requires-migration")
    lesson = (await client.get("/api/lessons/31")).json()

    async def absent(session):
        return False

    monkeypatch.setattr(editorial_history, "schema_available", absent)
    response = await client.post(
        f"/api/exercises/{lesson['exercises'][0]['id']}/attempt",
        headers=headers,
        json={"answer": "test", "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 503
    assert await session.scalar(select(func.count()).select_from(ExerciseAttempt)) == 0


async def test_concurrent_attempt_retries_capture_once(client, session):
    headers = await conta(client, "snapshot-concurrent")
    lesson = (await client.get("/api/lessons/31")).json()
    path = f"/api/exercises/{lesson['exercises'][0]['id']}/attempt"
    body = {"answer": "should", "idempotency_key": str(uuid4())}
    responses = await asyncio.gather(
        *(client.post(path, headers=headers, json=body) for _ in range(4))
    )
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["attempt_id"] for response in responses}) == 1
    assert await session.scalar(select(func.count()).select_from(ExerciseAttempt)) == 1
    assert await session.scalar(select(func.count()).select_from(EvidenceContentSnapshot)) == 1
