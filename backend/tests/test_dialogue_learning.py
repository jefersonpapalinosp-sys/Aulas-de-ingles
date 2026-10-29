"""BE-47: seis turnos, reentrega, escopo, revisão e recomendação explicada."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import (
    Course,
    DialogueTurn,
    Lesson,
    LessonProgress,
    ReviewItem,
    SkillEvidence,
    SpeakingDialogue,
    User,
)
from app.services import assistance, dialogue
from app.services.dialogue_learning import conversation_recommendation
from app.services.review import adicionar_cartas
from app.services.skills import skill_summaries
from tests.test_dashboard import conta


async def fixture_dialogue(session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_dialogue_url", "https://example.invalid/dialogue")
    calls = []

    def reply(*args, **kwargs):
        calls.append(1)
        return assistance.DialogueResult(
            raw={"partner_text": "Tell me more about your day.", "hints": [], "confidence": 0.9},
            cost_microusd=7,
            cost_known=True,
        )

    monkeypatch.setattr(assistance, "call_dialogue_provider", reply)
    user = User(email="dialogue-learning@example.com", password_hash="x", display_name="Teste")
    session.add(user)
    await session.flush()
    lesson = (await session.execute(select(Lesson).where(Lesson.number == 31))).scalar_one()
    conversation, brief = await dialogue.create_dialogue(
        session,
        user,
        lesson,
        mode="guided",
        operation_key=str(uuid4()),
    )
    # Recorte sintético curto: cada um dos dois termos é solicitado três vezes.
    brief = replace(brief, target_terms=brief.target_terms[:2])
    conversation.content_fingerprint = dialogue.content_fingerprint(brief)
    return user, lesson, conversation, brief, calls


async def complete(session, conversation, brief, position, text="I am practising today."):
    turn, _ = await dialogue.admit_turn(
        session,
        conversation,
        position,
        input_kind="text",
        transcript=text,
        idempotency_key=str(uuid4()),
    )
    await dialogue.resolve_turn(session, turn, conversation, brief, text)
    return turn


@pytest.mark.timezone
async def test_six_turns_create_six_evidences_and_two_cards_without_replay_cost(
    session, monkeypatch
):
    user, lesson, conversation, brief, calls = await fixture_dialogue(session, monkeypatch)
    turns = [await complete(session, conversation, brief, n) for n in range(1, 7)]
    evidence = (await session.scalars(select(SkillEvidence))).all()
    cards = (await session.scalars(select(ReviewItem))).all()
    assert len(evidence) == 6 and {e.source_id for e in evidence} == {t.id for t in turns}
    assert all(e.source_type == "dialogue_turn" and e.skill == "speaking" for e in evidence)
    assert len(cards) == 2
    assert all(card.origin_reason == "dialogue_missed_term" for card in cards)
    assert {card.vocab_item.term for card in cards} == set(brief.target_terms)
    assert all("I am practising" not in card.prompt + card.answer for card in cards)
    # Reentrega preserva inclusive uma carta já revisada/suspensa pelo aluno.
    cards[0].status = "suspended"
    cards[0].interval_days = 6
    cards[0].due_at = datetime.now(UTC) + timedelta(days=6)
    due = cards[0].due_at
    await session.flush()
    for turn in turns:
        outcome = await dialogue.resolve_turn(session, turn, conversation, brief, "Changed text")
        assert outcome.cost_microusd == 0
    assert len(calls) == 6
    assert await session.scalar(select(func.count()).select_from(SkillEvidence)) == 6
    assert await session.scalar(select(func.count()).select_from(ReviewItem)) == 2
    await session.refresh(cards[0])
    assert (cards[0].status, cards[0].interval_days, cards[0].due_at) == ("suspended", 6, due)
    assert turns[0].transcript == "I am practising today."
    skills = await skill_summaries(session, user.id, lesson.course.slug, lesson.unit.slug)
    speaking = next(skill for skill in skills if skill.skill == "speaking")
    assert speaking.samples == 6 and speaking.sources[0].source_type == "dialogue_turn"
    other = await skill_summaries(session, user.id, "voa-level-2")
    assert next(skill for skill in other if skill.skill == "speaking").samples == 0
    lesson.unit.status = "archived"
    await session.flush()
    assert all(skill.samples == 0 for skill in await skill_summaries(session, user.id))


async def test_one_miss_per_term_or_per_dialogue_does_not_create_review(session, monkeypatch):
    user, lesson, conversation, brief, _ = await fixture_dialogue(session, monkeypatch)
    await complete(session, conversation, brief, 1)
    await complete(session, conversation, brief, 2)
    assert await session.scalar(select(func.count()).select_from(ReviewItem)) == 0
    # O acerto do mesmo termo não é uma segunda falta.
    await complete(session, conversation, brief, 3, f"I can say {brief.target_terms[0]} today.")
    assert await session.scalar(select(func.count()).select_from(ReviewItem)) == 0
    second, _ = await dialogue.create_dialogue(
        session,
        user,
        lesson,
        mode="guided",
        operation_key=str(uuid4()),
    )
    await complete(session, second, brief, 1)
    assert await session.scalar(select(func.count()).select_from(ReviewItem)) == 0
    # Admissão pendente não é evidência de prática concluída.
    await dialogue.admit_turn(
        session,
        conversation,
        4,
        input_kind="text",
        transcript="Still waiting here.",
        idempotency_key=str(uuid4()),
    )
    assert await session.scalar(select(func.count()).select_from(SkillEvidence)) == 4


async def test_fallback_keeps_deterministic_evidence(session, monkeypatch):
    _, _, conversation, brief, _ = await fixture_dialogue(session, monkeypatch)

    def unavailable(*args, **kwargs):
        raise assistance.ProviderFailure("provider_unavailable")

    monkeypatch.setattr(assistance, "call_dialogue_provider", unavailable)
    turn = await complete(session, conversation, brief, 1)
    evidence = (await session.scalars(select(SkillEvidence))).one()
    assert turn.fallback
    assert evidence.score == sum(turn.checks.values()) / len(turn.checks)


async def test_deleting_dialogue_removes_only_its_learning(client, session):
    headers = await conta(client, "dialogue-delete-learning")
    lesson = (await session.execute(select(Lesson).where(Lesson.number == 31))).scalar_one()
    created = await client.post(
        "/api/speaking/dialogues",
        headers=headers,
        json={
            "lesson_id": lesson.id,
            "mode": "script",
            "operation_key": str(uuid4()),
        },
    )
    assert created.status_code == 201
    dialogue_id = created.json()["id"]
    # Dois ciclos de vocabulário em até 12 turnos, no conteúdo real da aula.
    for position in range(1, 13):
        result = await client.post(
            f"/api/speaking/dialogues/{dialogue_id}/turns/{position}/text",
            headers=headers,
            json={"text": "I am practising today.", "idempotency_key": str(uuid4())},
        )
        assert result.status_code == 202, result.text
    assert await session.scalar(select(func.count()).select_from(SkillEvidence)) == 12
    turn_ids = (await session.scalars(select(DialogueTurn.id))).all()
    assert await session.scalar(select(func.count()).select_from(ReviewItem)) == 1
    due = (await client.get("/api/review/due", headers=headers)).json()
    assert len(due) == 1 and "dois turnos da mesma conversa" in due[0]["reason"]
    # Outra origem de revisão não pode ser apagada junto.
    vocab = lesson.vocab[0]
    user = (await session.scalars(select(User))).one()
    assert await adicionar_cartas(session, user, [vocab]) == 1
    await session.commit()
    removed = await client.delete(f"/api/speaking/dialogues/{dialogue_id}", headers=headers)
    assert removed.status_code == 204
    assert (
        await session.scalar(
            select(func.count())
            .select_from(ReviewItem)
            .where(ReviewItem.source_type == "vocab_item")
        )
        == 1
    )
    assert await session.scalar(select(func.count()).select_from(SkillEvidence)) == 0
    assert (
        await session.scalar(
            select(func.count())
            .select_from(ReviewItem)
            .where(
                ReviewItem.source_type == "dialogue_turn",
                ReviewItem.source_id.in_(turn_ids),
            )
        )
        == 0
    )


@pytest.mark.timezone
@pytest.mark.parametrize("age_days,expected", [(6, False), (7, False), (8, True)])
async def test_recommendation_uses_seven_day_boundary_and_owner(
    session, monkeypatch, age_days, expected
):
    user, lesson, conversation, _, _ = await fixture_dialogue(session, monkeypatch)
    now = datetime.now(UTC)
    conversation.started_at = now - timedelta(days=age_days)
    session.add(LessonProgress(user_id=user.id, lesson_id=lesson.id))
    await session.flush()
    result = await conversation_recommendation(session, user.id, lesson.course, now)
    assert (result is not None) == expected
    if result:
        assert result.kind == "conversation" and result.lesson_number == 31
        assert "7 dias" in result.reason
    other = User(email="other-learning@example.com", password_hash="x", display_name="Outro")
    session.add(other)
    await session.flush()
    # Diálogo alheio recente não esconde a sugestão para quem estudou.
    session.add(LessonProgress(user_id=other.id, lesson_id=lesson.id))
    await session.flush()
    assert await conversation_recommendation(session, other.id, lesson.course, now)
    other_course = (await session.scalars(select(Course).where(Course.slug == "voa-level-2"))).one()
    assert await conversation_recommendation(session, user.id, other_course, now) is None


async def test_today_keeps_conversation_hidden_until_interface_release(
    client, session, monkeypatch
):
    headers = await conta(client, "dialogue-today")
    user_id = await session.scalar(
        select(User.id).where(User.email == "dialogue-today@example.com")
    )
    lesson = (await session.scalars(select(Lesson).where(Lesson.number == 31))).one()
    session.add(LessonProgress(user_id=user_id, lesson_id=lesson.id))
    await session.commit()
    assert get_settings().dialogue_practice_enabled is False
    assert (await client.get("/api/me/today", headers=headers)).json()["recommendation"][
        "kind"
    ] != "conversation"
    monkeypatch.setattr(get_settings(), "dialogue_practice_enabled", True)
    response = await client.get("/api/me/today", headers=headers)
    assert response.json()["recommendation"]["kind"] == "conversation"
    assert response.json()["recommendation"]["href"].endswith("/31/estudar/revisar#conversa")


async def test_concurrent_turns_create_one_card_and_replay_keeps_two_evidences(
    session, monkeypatch
):
    import asyncio

    from app.db.session import get_sessionmaker

    _, _, conversation, brief, calls = await fixture_dialogue(session, monkeypatch)
    brief = replace(brief, target_terms=brief.target_terms[:1])
    conversation.content_fingerprint = dialogue.content_fingerprint(brief)
    turns = []
    for position in (1, 2):
        turn, _ = await dialogue.admit_turn(
            session,
            conversation,
            position,
            input_kind="text",
            transcript="I am practising today.",
            idempotency_key=str(uuid4()),
        )
        turns.append(turn.id)
    await session.commit()

    async def resolve(turn_id):
        async with get_sessionmaker()() as connection, connection.begin():
            local_dialogue = await connection.get(SpeakingDialogue, conversation.id)
            turn = await connection.get(DialogueTurn, turn_id)
            await dialogue.resolve_turn(connection, turn, local_dialogue, brief, turn.transcript)

    await asyncio.gather(*(resolve(turn_id) for turn_id in turns))
    await asyncio.gather(*(resolve(turn_id) for turn_id in turns))
    assert len(calls) == 2
    assert await session.scalar(select(func.count()).select_from(SkillEvidence)) == 2
    assert await session.scalar(select(func.count()).select_from(ReviewItem)) == 1


@pytest.mark.timezone
async def test_worker_commits_learning_cost_and_job_together(session, monkeypatch):
    from app.db.models import AssistReservation, TranscriptionJob
    from app.services import assist_quota, transcription_queue

    _, _, conversation, _, _ = await fixture_dialogue(session, monkeypatch)
    turn, job = await dialogue.admit_turn(
        session,
        conversation,
        1,
        input_kind="text",
        transcript="I am practising today.",
        idempotency_key=str(uuid4()),
    )
    await session.commit()
    claim = await transcription_queue._claim_next_job(datetime.now(UTC))
    assert claim is not None and claim.job_id == job.id
    original = assist_quota.record_cost

    async def interrupt_commit(*args, **kwargs):
        raise RuntimeError("simulated failure before cost persistence")

    monkeypatch.setattr(assist_quota, "record_cost", interrupt_commit)
    with pytest.raises(RuntimeError, match="simulated failure"):
        await transcription_queue._process_dialogue_claim(claim)
    await session.refresh(turn)
    assert turn.state == "pending"
    assert await session.scalar(select(func.count()).select_from(SkillEvidence)) == 0
    monkeypatch.setattr(assist_quota, "record_cost", original)
    assert await transcription_queue._process_dialogue_claim(claim)
    await session.refresh(turn)
    await session.refresh(job)
    reservation = await session.get(AssistReservation, claim.reservation_id)
    assert turn.state == job.status == "completed"
    assert turn.cost_microusd == reservation.cost_microusd == 7
    assert reservation.cost_known
    assert await session.scalar(select(func.count()).select_from(SkillEvidence)) == 1
    # Claim já concluído não gera outra evidência nem cobra novamente.
    assert await transcription_queue._process_dialogue_claim(claim)
    assert await session.scalar(select(func.count()).select_from(SkillEvidence)) == 1
    assert (await session.get(TranscriptionJob, job.id)).status == "completed"
