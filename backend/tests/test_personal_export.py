"""Portabilidade v2 no PostgreSQL descartável; nenhum provedor externo."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update

from app.core.config import get_settings
from app.db.models import (
    AssistReservation,
    Base,
    DialogueTurn,
    Lesson,
    NotebookEntry,
    SpeakingDialogue,
    TranscriptionJob,
    User,
)
from app.db.session import get_sessionmaker
from app.services import personal_export
from tests.audio_samples import encoded
from tests.test_assist_quota import audio_attempt
from tests.test_course_reviews import REVIEW_URL, attempt_body
from tests.test_notebook import conta
from tests.test_practice import create_body


def test_inventory_covers_every_personal_model():
    owned = {t.name for t in Base.metadata.tables.values() if "user_id" in t.c}
    assert owned == {m.__tablename__ for m in personal_export.PERSONAL_MODELS}
    assert {c.__tablename__ for c, _, _ in personal_export.CHILD_MODELS} == {
        "writing_revision",
        "step_progress",
        "practice_session_item",
    }


async def test_new_modalities_orphan_feedback_and_account_isolation(client, session):
    a = await conta(client, "complete-a")
    lesson = (await client.get("/api/lessons/31")).json()
    prompt_id = lesson["writing_prompts"][0]["id"]
    feedback = await client.post(
        f"/api/writing/prompts/{prompt_id}/feedback",
        headers=a,
        json={"text": "My train is faster than a bus. You should try it."},
    )
    assert feedback.status_code == 200
    practice = await client.post(
        "/api/courses/voa-level-1/lessons/31/practice-sessions", headers=a, json=create_body()
    )
    assert practice.status_code == 201, practice.text
    practice = practice.json()
    attempt = await client.post(
        f"/api/exercises/{practice['items'][0]['exercise']['id']}/attempt",
        headers=a,
        json={
            "answer": "synthetic answer",
            "idempotency_key": str(uuid4()),
            "practice_session_id": practice["id"],
        },
    )
    assert attempt.status_code == 200
    review = (await client.get(REVIEW_URL, headers=a)).json()
    checkpoint = await client.post(f"{REVIEW_URL}/attempts", headers=a, json=attempt_body(review))
    assert checkpoint.status_code == 201, checkpoint.text
    await client.put("/api/lessons/31/studied", headers=a)
    due = (await client.get("/api/review/due", headers=a)).json()[0]
    grade = await client.post(
        f"/api/review/{due['id']}/grade",
        headers=a,
        json={"quality": 4, "expected_revision": due["revision"], "idempotency_key": str(uuid4())},
    )
    assert grade.status_code == 200
    # O recibo deve continuar no export mesmo se o item foi removido.
    assert (await client.delete(f"/api/review/{due['id']}", headers=a)).status_code == 204
    user_id = await session.scalar(
        select(User.id).where(User.email == "caderno-complete-a@exemplo.com")
    )
    now = datetime.now(UTC)
    session.add(
        AssistReservation(
            user_id=user_id,
            request_key=str(uuid4()),
            fingerprint="f" * 64,
            provider_key="secret-provider-key",
            modality="writing",
            state="released",
            cost_microusd=0,
            cost_known=True,
            created_at=now,
            expires_at=now + timedelta(minutes=5),
        )
    )
    await session.commit()
    data = (await client.get("/api/me/export", headers=a)).json()
    assert data["writing"] == []  # Feedback sem rascunho continua exportável.
    assert data["writing_feedback"][0]["id"] == feedback.json()["id"]
    assert data["writing_feedback"][0]["rubric_snapshot"]
    assert data["practice_sessions"][0]["id"] == practice["id"]
    assert len(data["practice_items"]) == len(practice["items"])
    assert data["exercise_attempts"][0]["practice_session_item_id"] in {
        i["id"] for i in data["practice_items"]
    }
    assert data["exercise_attempts"][0]["historical_content_status"] == "unavailable"
    assert data["checkpoint_attempts"][0]["result"]
    assert data["checkpoint_attempts"][0]["content_version"] == review["content_version"]
    assert data["checkpoint_attempts"][0]["unit_slug"] == "40-44"
    assert data["review_events"][0]["item_id"] is None
    assert data["review_events"][0]["before_state"]
    assert data["assistance_usage"][0]["state"] == "released"
    assert data["login_sessions"]
    assert "secret-provider-key" not in str(data)
    assert data["scope"]["row_counts"]["writing_feedback"] == 1
    b = await conta(client, "complete-b")
    exported = await client.get("/api/me/export", headers=b)
    assert exported.status_code == 200
    assert "no-store" in exported.headers["cache-control"]
    other = exported.json()
    for section in (
        "writing_feedback",
        "checkpoint_attempts",
        "practice_sessions",
        "practice_items",
        "exercise_attempts",
        "review_events",
        "assistance_usage",
        "legacy_review_cards",
        "audio_manifest",
        "dialogues",
        "dialogue_turns",
    ):
        assert other[section] == []
    assert all(
        item["id"] not in {s["id"] for s in data["login_sessions"]}
        for item in other["login_sessions"]
    )


async def test_dialogues_and_turns_are_exported_only_to_their_owner(client, session):
    a = await conta(client, "dialogue-a")
    b = await conta(client, "dialogue-b")
    owner = await session.scalar(
        select(User.id).where(User.email == "caderno-dialogue-a@exemplo.com")
    )
    lesson_id = await session.scalar(select(Lesson.id).order_by(Lesson.id).limit(1))
    dialogue = SpeakingDialogue(
        user_id=owner,
        lesson_id=lesson_id,
        operation_key=str(uuid4()),
        mode="guided",
        content_version=1,
        content_fingerprint="a" * 64,
        provider_name="cloudflare-workers-ai",
        rubric_version="dialogue-prompt-v1",
    )
    session.add(dialogue)
    await session.flush()
    expires_at = datetime.now(UTC) + timedelta(days=30)
    session.add_all(
        [
            DialogueTurn(
                dialogue_id=dialogue.id,
                user_id=owner,
                position=1,
                role="partner",
                state="completed",
                partner_text="Hello! What do you do every day?",
                expires_at=expires_at,
            ),
            DialogueTurn(
                dialogue_id=dialogue.id,
                user_id=owner,
                position=2,
                role="student",
                input_kind="text",
                state="completed",
                transcript="I am a student.",
                checks={"target_terms_missing": True, "too_short": False},
                cost_microusd=12,
                expires_at=expires_at,
            ),
        ]
    )
    await session.commit()
    exported = await client.get("/api/me/export", headers=a)
    assert exported.status_code == 200, exported.text
    data = exported.json()
    assert data["schema_version"] == "2.1"
    assert [item["mode"] for item in data["dialogues"]] == ["guided"]
    assert data["dialogues"][0]["operation_key"] == dialogue.operation_key
    assert [turn["position"] for turn in data["dialogue_turns"]] == [1, 2]
    assert data["dialogue_turns"][1]["transcript"] == "I am a student."
    assert data["dialogue_turns"][1]["checks"] == {"target_terms_missing": True, "too_short": False}
    assert data["dialogue_turns"][0]["hints"] == []
    assert data["scope"]["row_counts"]["speaking_dialogue"] == 1
    assert data["scope"]["row_counts"]["dialogue_turn"] == 2
    other = (await client.get("/api/me/export", headers=b)).json()
    assert other["dialogues"] == [] and other["dialogue_turns"] == []
    assert other["scope"]["row_counts"]["dialogue_turn"] == 0


async def test_snapshot_is_read_only_and_ignores_concurrent_commits(client, monkeypatch):
    headers = await conta(client, "snapshot")
    created = await client.post(
        "/api/me/notebook",
        headers=headers,
        json={"lesson_number": 31, "kind": "note", "content": "Before snapshot"},
    )
    entry_id = created.json()["id"]
    original = personal_export._inventory

    async def concurrent_write(session, user_id, now):
        counts = await original(session, user_id, now)
        assert await session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        assert await session.scalar(text("SHOW transaction_read_only")) == "on"
        async with get_sessionmaker()() as writer:
            await writer.execute(
                update(NotebookEntry)
                .where(NotebookEntry.id == entry_id)
                .values(content="After snapshot")
            )
            await writer.execute(
                update(User).where(User.id == user_id).values(display_name="Changed concurrently")
            )
            await writer.commit()
        return counts

    monkeypatch.setattr(personal_export, "_inventory", concurrent_write)
    exported = await client.get("/api/me/export", headers=headers)
    assert exported.status_code == 200, exported.text
    data = exported.json()
    assert data["notebook"][0]["content"] == "Before snapshot"
    assert data["profile"]["display_name"] == "snapshot"
    assert data["exported_at"] == data["scope"]["snapshot_at"]
    # O read-only não vaza para o próximo comando/checkout da conexão.
    changed = await client.put(
        f"/api/me/notebook/{entry_id}",
        headers=headers,
        json={"kind": "note", "content": "Normal write afterwards"},
    )
    assert changed.status_code == 200


@pytest.mark.parametrize("limit", ["MAX_RECORDS", "MAX_JSON_BYTES"])
async def test_export_limits_fail_whole_request_without_partial_file(client, monkeypatch, limit):
    headers = await conta(client, f"limit-{limit.lower()}")
    monkeypatch.setattr(personal_export, limit, 1)
    response = await client.get("/api/me/export", headers=headers)
    assert response.status_code == 413
    assert "content-disposition" not in response.headers
    assert "profile" not in response.json()
    assert "no-store" in response.headers["cache-control"]


async def test_export_timeout_releases_transaction_and_can_retry(client, monkeypatch):
    headers = await conta(client, "timeout")
    original = personal_export._complete_export

    async def blocked(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(personal_export, "EXPORT_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(personal_export, "_complete_export", blocked)
    response = await client.get("/api/me/export", headers=headers)
    assert response.status_code == 503
    monkeypatch.setattr(personal_export, "_complete_export", original)
    monkeypatch.setattr(personal_export, "EXPORT_TIMEOUT_SECONDS", 20)
    assert (await client.get("/api/me/export", headers=headers)).status_code == 200


async def test_audio_manifest_auth_integrity_and_expired_transcription(
    client, session, monkeypatch, tmp_path
):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    a = await conta(client, "audio-manifest")
    attempt_id = await audio_attempt(client, a)
    user_id = await session.scalar(
        select(User.id).where(User.email == "caderno-audio-manifest@exemplo.com")
    )
    session.add(
        TranscriptionJob(
            user_id=user_id,
            speaking_attempt_id=attempt_id,
            provider="synthetic",
            idempotency_key=str(uuid4()),
            status="completed",
            transcript_text="EXPIRED SHOULD NOT LEAK",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    await session.commit()
    exported = await client.get("/api/me/export", headers=a)
    assert exported.status_code == 200
    data = exported.json()
    audio = data["audio_manifest"][0]
    assert audio["attempt_id"] == attempt_id
    assert audio["sha256"] and audio["integrity_state"] == "verified"
    assert data["speaking"][0]["transcription"] is None
    assert data["scope"]["row_counts"]["transcription_job"] == 0
    assert "EXPIRED" not in exported.text
    assert "storage_key" not in exported.text
    assert data["scope"]["includes_audio_bytes"] is False
    path = audio["download_path"]
    assert (await client.get(path)).status_code == 401
    b = await conta(client, "other-audio")
    assert (await client.get(path, headers=b)).status_code == 404
    download = await client.get(path, headers=a)
    assert download.status_code == 200 and download.content == encoded()
    assert "no-store" in download.headers["cache-control"]
    assert (
        await client.delete(f"/api/speaking/attempts/{attempt_id}", headers=a)
    ).status_code == 204
    assert (await client.get(path, headers=a)).status_code == 404
