"""Piloto por conta: admissão, revogação e despacho antes de STT/LLM."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.models import AssistReservation, DialogueTurn, TranscriptionJob
from app.services import assistance, transcription_queue
from tests.audio_samples import wav
from tests.test_auth import auth, registrar
from tests.test_dialogue_frontend_contract import audio_turn
from tests.test_dialogue_routes import _criar


@pytest.mark.parametrize("env,profile", [("prod", "local"), ("dev", "public"), ("test", "public")])
def test_empty_pilot_fails_closed_on_production_or_public(env, profile):
    settings = Settings(app_env=env, deployment_profile=profile, dialogue_pilot_user_ids=[])
    assert not settings.dialogue_account_allowed(1)
    settings.dialogue_pilot_user_ids = [7]
    assert settings.dialogue_account_allowed(7)
    assert not settings.dialogue_account_allowed(1)


@pytest.mark.parametrize("env", ["dev", "test"])
def test_local_rehearsals_and_explicit_restriction(env):
    settings = Settings(app_env=env, deployment_profile="local", dialogue_pilot_user_ids=[])
    assert settings.dialogue_account_allowed(1)
    settings.dialogue_pilot_user_ids = [7]
    assert not settings.dialogue_account_allowed(1)
    assert settings.dialogue_account_allowed(7)


@pytest.mark.parametrize("value", ["[true]", '["7"]', "[0]", "[-1]", "[1.5]", '"7"'])
def test_pilot_env_requires_json_positive_integer_ids(monkeypatch, value):
    monkeypatch.setenv("DIALOGUE_PILOT_USER_IDS", value)
    with pytest.raises(ValidationError):
        Settings()


def test_pilot_env_accepts_json_ids(monkeypatch):
    monkeypatch.setenv("DIALOGUE_PILOT_USER_IDS", "[7, 9]")
    assert Settings().dialogue_pilot_user_ids == [7, 9]


async def account(client, suffix):
    headers = auth(await registrar(client, suffix))
    uid = (await client.get("/api/auth/me", headers=headers)).json()["id"]
    return headers, uid


def enable(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "dialogue_practice_enabled", True)
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_dialogue_url", "https://invalid.test/dialogue")
    monkeypatch.setattr(settings, "assist_transcription_url", "https://invalid.test/stt")
    return settings


async def text_turn(client, headers, did):
    return await client.post(
        f"/api/speaking/dialogues/{did}/turns/1/text",
        headers=headers,
        json={"text": "I take the bus.", "idempotency_key": str(uuid4())},
    )


async def test_only_pilot_can_create_assisted_but_script_remains_available(
    client, session, monkeypatch
):
    settings = enable(monkeypatch)
    allowed, uid = await account(client, "pilot-allowed")
    denied, _ = await account(client, "pilot-denied")
    monkeypatch.setattr(settings, "dialogue_pilot_user_ids", [uid])
    for headers, permitted in [(allowed, True), (denied, False)]:
        status = (await client.get("/api/speaking/dialogues/status", headers=headers)).json()
        assert status["guided_enabled"] == status["audio_enabled"] == permitted
        for mode in ["guided", "free_unit"]:
            code, body = await _criar(client, headers, mode=mode)
            assert code == (201 if permitted else 409), body
    _, script = await _criar(client, denied)
    turn = await text_turn(client, denied, script["id"])
    assert turn.status_code == 202 and turn.json()["state"] == "completed"
    assert (await session.scalars(select(TranscriptionJob))).all() == []
    assert (await session.scalars(select(AssistReservation))).all() == []


async def test_revoked_account_cannot_submit_text_or_audio_but_can_read_export_delete(
    client, session, monkeypatch, tmp_path
):
    settings = enable(monkeypatch)
    headers, uid = await account(client, "pilot-revoked")
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    _, conversation = await _criar(client, headers, mode="guided")
    did = conversation["id"]
    monkeypatch.setattr(settings, "dialogue_pilot_user_ids", [uid + 1])
    denied = await text_turn(client, headers, did)
    assert denied.status_code == 409 and denied.json()["detail"]["code"] == "assist_disabled"
    denied = await client.put(
        f"/api/speaking/dialogues/{did}/turns/1/audio",
        content=wav(),
        headers={**headers, "Content-Type": "audio/wav", "X-Audio-Consent": "true"},
    )
    assert denied.status_code == 409 and not list(tmp_path.iterdir())
    assert (await session.scalars(select(AssistReservation))).all() == []
    assert (await session.scalars(select(DialogueTurn))).all() == []
    assert (await session.scalars(select(TranscriptionJob))).all() == []
    assert (await client.get(f"/api/speaking/dialogues/{did}", headers=headers)).status_code == 200
    assert (await client.get("/api/me/export", headers=headers)).json()["dialogues"][0]["id"] == did
    assert (
        await client.delete(f"/api/speaking/dialogues/{did}", headers=headers)
    ).status_code == 204


async def test_denied_queued_account_does_not_consume_attempt_or_starve_allowed_job(
    client, session, monkeypatch
):
    settings = enable(monkeypatch)
    denied, _ = await account(client, "pilot-queue-denied")
    allowed, uid = await account(client, "pilot-queue-allowed")
    job_ids = []
    for headers in [denied, allowed]:
        _, conversation = await _criar(client, headers, mode="guided")
        response = await text_turn(client, headers, conversation["id"])
        assert response.status_code == 202, response.text
        job_ids.append(response.json()["job_id"])
    monkeypatch.setattr(settings, "dialogue_pilot_user_ids", [uid])
    claim = await transcription_queue._claim_next_job(datetime.now(UTC))
    assert claim and claim.job_id == job_ids[1]
    assert await transcription_queue._claim_next_job(datetime.now(UTC)) is None
    denied_job = await session.get(TranscriptionJob, job_ids[0])
    assert denied_job.status == "queued" and denied_job.attempt_count == 0
    reservation = await session.get(AssistReservation, denied_job.assist_reservation_id)
    assert reservation.state == "reserved"


async def test_revocation_after_claim_blocks_stt_and_releases_unconsumed_quota(
    client, session, monkeypatch, tmp_path
):
    headers, did = await audio_turn(client, monkeypatch, tmp_path)
    claim = await transcription_queue._claim_next_job(datetime.now(UTC))
    assert claim is not None
    uid = (await client.get("/api/auth/me", headers=headers)).json()["id"]
    monkeypatch.setattr(get_settings(), "dialogue_pilot_user_ids", [uid + 1])

    def unexpected(*args, **kwargs):
        pytest.fail("Conta revogada não pode enviar áudio ou texto ao provedor")

    monkeypatch.setattr(assistance, "call_transcription_provider", unexpected)
    monkeypatch.setattr(assistance, "call_dialogue_provider", unexpected)
    assert await transcription_queue._process_dialogue_claim(claim)
    reservation = (await session.scalars(select(AssistReservation))).one()
    job = await session.get(TranscriptionJob, claim.job_id)
    assert reservation.state == "released"
    assert job.status == "failed" and job.error_code == "assist_disabled"
    response = await client.get(f"/api/speaking/dialogues/{did}/turns/1", headers=headers)
    assert response.json()["state"] == "failed"


async def test_public_empty_list_blocks_existing_queue(client, session, monkeypatch, tmp_path):
    await audio_turn(client, monkeypatch, tmp_path)
    monkeypatch.setattr(get_settings(), "deployment_profile", "public")
    monkeypatch.setattr(get_settings(), "dialogue_pilot_user_ids", [])
    assert not await transcription_queue.process_next_transcription()
    job = (await session.scalars(select(TranscriptionJob))).one()
    assert job.status == "queued" and job.attempt_count == 0
    assert (await session.scalars(select(AssistReservation))).one().state == "reserved"


async def test_explicit_pilot_can_finish_audio_turn(client, session, monkeypatch, tmp_path):
    headers, did = await audio_turn(client, monkeypatch, tmp_path)
    uid = (await client.get("/api/auth/me", headers=headers)).json()["id"]
    monkeypatch.setattr(get_settings(), "dialogue_pilot_user_ids", [uid])
    calls = []

    def stt(*args, **kwargs):
        calls.append("stt")
        return assistance.TranscriptionResult("I take the bus.", [], 0.9, 0)

    def partner(*args, **kwargs):
        calls.append("dialogue")
        return assistance.DialogueResult(
            {"partner_text": "Where do you go?", "hints": [], "confidence": 0.9}, 0, True
        )

    monkeypatch.setattr(assistance, "call_transcription_provider", stt)
    monkeypatch.setattr(assistance, "call_dialogue_provider", partner)
    assert await transcription_queue.process_next_transcription()
    assert calls == ["stt", "dialogue"]
    assert (await session.scalars(select(AssistReservation))).one().state == "consumed"
    response = await client.get(f"/api/speaking/dialogues/{did}/turns/1", headers=headers)
    assert response.json()["state"] == "completed"
