"""FE-47: cota própria, falha terminal e confiança real da transcrição."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AssistReservation, DialogueTurn, TranscriptionJob
from app.services import assistance, transcription_queue
from tests.audio_samples import wav
from tests.test_auth import auth, registrar
from tests.test_dialogue_routes import _criar


async def test_dialogue_status_is_private_gated_and_has_own_quota(client, monkeypatch):
    settings = get_settings()
    headers = auth(await registrar(client, "fe47-status"))
    monkeypatch.setattr(settings, "dialogue_practice_enabled", False)
    response = await client.get("/api/speaking/dialogues/status", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert not response.json()["enabled"] and not response.json()["guided_enabled"]
    monkeypatch.setattr(settings, "dialogue_practice_enabled", True)
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_dialogue_url", "https://invalid.test/dialogue")
    monkeypatch.setattr(settings, "assist_transcription_url", "https://invalid.test/stt")
    monkeypatch.setattr(settings, "assist_dialogue_daily_turns", 12)
    monkeypatch.setattr(settings, "assist_daily_quota", 5)
    body = (await client.get("/api/speaking/dialogues/status", headers=headers)).json()
    assert body["enabled"] and body["guided_enabled"] and body["audio_enabled"]
    assert body["remaining_today"] == body["daily_quota"] == 12
    assert (await client.get("/api/speaking/dialogues/status")).status_code == 401


async def audio_turn(client, monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_provider_kind", "gateway")
    monkeypatch.setattr(settings, "assist_dialogue_url", "https://invalid.test/dialogue")
    monkeypatch.setattr(settings, "assist_transcription_url", "https://invalid.test/stt")
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    headers = auth(await registrar(client, "fe47-audio"))
    _, conversation = await _criar(client, headers, mode="guided")
    response = await client.put(
        f"/api/speaking/dialogues/{conversation['id']}/turns/1/audio",
        content=wav(),
        headers={**headers, "Content-Type": "audio/wav", "X-Audio-Consent": "true"},
    )
    assert response.status_code == 202, response.text
    return headers, conversation["id"]


async def test_script_audio_is_rejected_before_storage(client, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers = auth(await registrar(client, "fe47-script"))
    _, conversation = await _criar(client, headers)
    response = await client.put(
        f"/api/speaking/dialogues/{conversation['id']}/turns/1/audio",
        content=wav(),
        headers={**headers, "Content-Type": "audio/wav", "X-Audio-Consent": "true"},
    )
    assert response.status_code == 409 and not list(tmp_path.iterdir())


@pytest.mark.timezone
async def test_audio_confidence_and_combined_cost_reach_the_private_turn(
    client, session, monkeypatch, tmp_path
):
    headers, did = await audio_turn(client, monkeypatch, tmp_path)
    calls = []
    words = [{"text": "bus", "start_ms": 0, "end_ms": 500, "confidence": 0.6}]

    def stt(*args, **kwargs):
        calls.append("stt")
        return assistance.TranscriptionResult("I take the bus.", words, 0.6, 3)

    def partner(*args, **kwargs):
        calls.append("dialogue")
        return assistance.DialogueResult(
            {"partner_text": "Where do you go?", "hints": [], "confidence": 0.9}, 7, True
        )

    monkeypatch.setattr(assistance, "call_transcription_provider", stt)
    monkeypatch.setattr(assistance, "call_dialogue_provider", partner)
    claim = await transcription_queue._claim_next_job(datetime.now(UTC))
    assert claim is not None
    assert await transcription_queue._process_dialogue_claim(claim)
    turn = (await session.scalars(select(DialogueTurn))).one()
    reservation = (await session.scalars(select(AssistReservation))).one()
    assert turn.cost_microusd == reservation.cost_microusd == 10
    assert reservation.cost_known
    response = await client.get(f"/api/speaking/dialogues/{did}", headers=headers)
    assert response.json()["turns"][0]["words"] == words
    response = await client.get(f"/api/speaking/dialogues/{did}/turns/1", headers=headers)
    assert response.json()["words"] == words
    assert await transcription_queue._process_dialogue_claim(claim)
    assert calls == ["stt", "dialogue"]
    exported = await client.get("/api/me/export", headers=headers)
    assert exported.status_code == 200
    data = exported.json()
    audio = data["speaking"][0]
    assert audio["origin"] == "dialogue" and audio["cue_id"] is None
    assert audio["cue_text"] is None
    assert audio["lesson_id"] == data["dialogues"][0]["lesson_id"]
    assert data["dialogue_turns"][0]["speaking_attempt_id"] == audio["id"]
    assert data["audio_manifest"][0]["download_path"]
    assert (
        await client.delete(f"/api/speaking/dialogues/{did}", headers=headers)
    ).status_code == 204
    assert (await session.scalars(select(TranscriptionJob))).all() == []
    # Excluir a conversa não remove o áudio antes da política de retenção.
    # A portabilidade ainda precisa funcionar sem cue ou diálogo associado.
    exported = await client.get("/api/me/export", headers=headers)
    assert exported.status_code == 200
    data = exported.json()
    assert data["dialogues"] == data["dialogue_turns"] == []
    assert data["speaking"][0]["id"] == audio["id"]
    assert data["speaking"][0]["lesson_id"] is None
    assert data["speaking"][0]["transcription"] is None
    await session.refresh(reservation)
    assert reservation.state == "consumed" and reservation.cost_microusd == 10


@pytest.mark.timezone
async def test_expired_reservation_does_not_dispatch_audio_and_is_terminal_in_ui(
    client, session, monkeypatch, tmp_path
):
    headers, did = await audio_turn(client, monkeypatch, tmp_path)
    reservation = (await session.scalars(select(AssistReservation))).one()
    reservation.created_at = datetime.now(UTC) - timedelta(days=2)
    reservation.expires_at = datetime.now(UTC) - timedelta(days=1)
    await session.commit()

    def never(*args, **kwargs):
        raise AssertionError("STT não pode preceder a autorização da reserva")

    monkeypatch.setattr(assistance, "call_transcription_provider", never)
    claim = await transcription_queue._claim_next_job(datetime.now(UTC))
    assert claim is not None
    assert await transcription_queue._process_dialogue_claim(claim)
    job = (await session.scalars(select(TranscriptionJob))).one()
    assert job.status == "failed"
    response = await client.get(f"/api/speaking/dialogues/{did}", headers=headers)
    assert response.json()["turns"][0]["state"] == "failed"
    response = await client.get(f"/api/speaking/dialogues/{did}/turns/1", headers=headers)
    assert response.json()["state"] == "failed"
    assert response.json()["error_code"] == "reservation_unavailable"
