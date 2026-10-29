"""IA-48: evidência do Guiado, sem conteúdo pessoal ou mistura de modalidades."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app import cli
from app.core.config import Settings, get_settings
from app.db.models import (
    AssistReservation,
    DialogueTurn,
    Lesson,
    SpeakingDialogue,
    TranscriptionJob,
    User,
)
from app.services import assistance, transcription_queue
from app.services.assist_gate import collect_gate_metrics, evaluate_gate
from tests.test_assist_gate import approved_review
from tests.test_auth import auth, registrar
from tests.test_dialogue_routes import _criar


async def add_turn(
    session,
    user,
    lesson,
    *,
    mode="guided",
    provider="pilot-provider",
    state="completed",
    fallback=False,
    error=None,
    rating="helpful",
    role="student",
    cost=10,
    known=True,
    with_job=True,
):
    now = datetime.now(UTC)
    dialogue = SpeakingDialogue(
        user_id=user.id,
        lesson_id=lesson.id,
        operation_key=str(uuid4()),
        mode=mode,
        content_version=1,
        content_fingerprint="f" * 64,
        provider_name=provider,
        rubric_version="dialogue-prompt-v1",
    )
    session.add(dialogue)
    await session.flush()
    job = None
    if with_job:
        reservation = AssistReservation(
            user_id=user.id,
            request_key=str(uuid4()),
            fingerprint="f" * 64,
            modality="conversation",
            provider_key=uuid4().hex,
            state="consumed",
            cost_microusd=cost,
            cost_known=known,
            created_at=now,
            expires_at=now + timedelta(days=1),
        )
        session.add(reservation)
        await session.flush()
        job = TranscriptionJob(
            user_id=user.id,
            kind="dialogue",
            provider=provider,
            assist_reservation_id=reservation.id,
            idempotency_key=uuid4().hex,
            status="completed"
            if state == "completed"
            else "failed"
            if state == "failed"
            else "queued",
            cost_microusd=cost,
            human_rating=rating,
            expires_at=now + timedelta(days=30),
        )
        session.add(job)
        await session.flush()
    turn = DialogueTurn(
        dialogue_id=dialogue.id,
        user_id=user.id,
        position=1,
        role=role,
        input_kind="text" if role == "student" else None,
        transcription_job_id=job.id if job else None,
        state=state,
        fallback=fallback,
        error_code=error,
        human_rating=rating,
        cost_microusd=cost,
        transcript="private student text",
        partner_text="private partner text",
        expires_at=now + timedelta(days=30),
    )
    session.add(turn)
    await session.flush()
    return turn


@pytest.mark.timezone
async def test_gate_agrega_so_guiado_do_provedor_e_conta_fallback_como_falha(session):
    user = User(email="gate@example.test", password_hash="x", display_name="Private Name")
    session.add(user)
    await session.flush()
    lessons = list((await session.scalars(select(Lesson).order_by(Lesson.id).limit(5))).all())
    for i in range(30):
        await add_turn(
            session,
            user,
            lessons[i % 5],
            rating="helpful" if i < 24 else "not_helpful",
        )
    # Estes registros não podem inflar a aprovação nem o orçamento do Guiado.
    for excluded in (
        {"mode": "script"},
        {"mode": "free_unit"},
        {"provider": "previous-provider"},
        {"role": "partner"},
    ):
        await add_turn(session, user, lessons[0], cost=9999, **excluded)
    metrics = await collect_gate_metrics(session, "conversation", provider_name="pilot-provider")
    assert (metrics.total, metrics.successful, metrics.rated, metrics.helpful) == (30, 30, 30, 24)
    assert metrics.rated_lessons == 5 and metrics.cost_microusd == 300
    settings = Settings(assist_provider_name="pilot-provider", assist_dialogue_url="https://test")
    review = replace(approved_review(), modality="conversation")
    assert evaluate_gate("conversation", metrics, review, settings).approved

    await add_turn(session, user, lessons[0], fallback=True, error="provider_unavailable")
    await add_turn(session, user, lessons[0], state="failed", known=False)
    await add_turn(session, user, lessons[0], error="invalid_provider_response", with_job=False)
    await add_turn(session, user, lessons[0], state="pending", cost=0, rating=None, known=False)
    metrics = await collect_gate_metrics(session, "conversation", provider_name="pilot-provider")
    assert (metrics.total, metrics.successful, metrics.failed) == (34, 30, 3)
    assert (metrics.rated, metrics.helpful, metrics.rated_lessons) == (30, 24, 5)
    assert metrics.cost_microusd == 330  # Já inclui STT; não somar custo do job.
    assert metrics.unknown_cost_turns == 2
    report = evaluate_gate("conversation", metrics, review, settings)
    assert set(report.blocking_reasons) == {"technical_failure_rate", "cost_known"}
    serialized = json.dumps(report.as_dict())
    for private in ("private student text", "private partner text", user.email, user.display_name):
        assert private not in serialized
    # O gate antigo de transcrição também deve ignorar os jobs de diálogo.
    legacy = await collect_gate_metrics(session, "transcription")
    assert legacy.total == legacy.cost_microusd == legacy.rated == 0
    with pytest.raises(ValueError, match="nome do provedor"):
        await collect_gate_metrics(session, "conversation")


async def test_cli_conversation_sem_evidencia_reprova_com_json_agregado(
    session,
    tmp_path,
    capsys,
    monkeypatch,
):
    payload = json.loads(
        (
            Path(__file__).resolve().parents[2] / "config/assist-provider-review.example.json"
        ).read_text()
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(payload))
    monkeypatch.setattr(get_settings(), "assist_provider_name", payload["provider_name"])
    assert not await cli._assist_gate("conversation", review_path)
    report = json.loads(capsys.readouterr().out)
    assert report["modality"] == "conversation"
    assert report["metrics"]["total"] == 0
    assert "minimum_human_ratings" in report["blocking_reasons"]
    assert "minimum_rated_lessons" in report["blocking_reasons"]


@pytest.mark.timezone
@pytest.mark.parametrize("known", [True, False])
async def test_worker_distingue_custo_zero_confirmado_de_custo_desconhecido(
    client,
    session,
    monkeypatch,
    known,
):
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_provider_kind", "gateway")
    monkeypatch.setattr(settings, "assist_provider_name", "pilot-provider")
    monkeypatch.setattr(settings, "assist_dialogue_url", "https://invalid.test/dialogue")
    headers = auth(await registrar(client, "gate-zero-cost"))
    _, conversation = await _criar(client, headers, mode="guided")
    response = await client.post(
        f"/api/speaking/dialogues/{conversation['id']}/turns/1/text",
        headers=headers,
        json={"text": "The train is faster than the bus.", "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 202

    def partner(*args, **kwargs):
        return assistance.DialogueResult(
            {"partner_text": "Where do you go?", "hints": [], "confidence": 0.9},
            0,
            known,
        )

    monkeypatch.setattr(assistance, "call_dialogue_provider", partner)
    claim = await transcription_queue._claim_next_job(datetime.now(UTC))
    assert claim is not None
    assert await transcription_queue._process_dialogue_claim(claim)
    reservation = (await session.scalars(select(AssistReservation))).one()
    assert reservation.cost_microusd == 0 and reservation.cost_known is known
    metrics = await collect_gate_metrics(session, "conversation", provider_name="pilot-provider")
    assert metrics.successful == 1 and metrics.cost_microusd == 0
    assert metrics.unknown_cost_turns == (0 if known else 1)
