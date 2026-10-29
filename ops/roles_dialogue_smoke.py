"""BE-47: criação na API e resultado no worker com os papéis reais do laboratório."""

import asyncio
import os
from uuid import uuid4

from app.core.config import get_settings
from app.db.models import (
    DialogueTurn,
    Lesson,
    ReviewItem,
    SkillEvidence,
    SpeakingDialogue,
    User,
)
from app.db.session import dispose_engine, get_sessionmaker
from app.services import assistance, dialogue
from sqlalchemy import func, select


def provider(*args: object, **kwargs: object) -> assistance.DialogueResult:
    return assistance.DialogueResult(
        raw={
            "partner_text": "Tell me more about your day.",
            "hints": [],
            "confidence": 0.9,
        },
        cost_microusd=1,
        cost_known=True,
    )


async def main() -> None:
    assert os.environ["DATABASE_URL"].endswith("@db:5432/aulas_roles_lab")
    assert os.environ["DATABASE_PURPOSE"] in {"runtime", "worker"}
    settings = get_settings()
    previous_enabled = settings.assisted_features_enabled
    previous_url = settings.assist_dialogue_url
    previous_provider = assistance.call_dialogue_provider
    settings.assisted_features_enabled = True
    settings.assist_dialogue_url = "https://example.invalid/dialogue"
    assistance.call_dialogue_provider = provider
    try:
        async with get_sessionmaker()() as session, session.begin():
            if os.environ["DATABASE_PURPOSE"] == "runtime":
                user = User(
                    email=f"roles-dialogue-{uuid4().hex}@example.invalid",
                    password_hash="!disabled!",
                    display_name="synthetic",
                )
                session.add(user)
                await session.flush()
                lesson = (
                    await session.scalars(select(Lesson).where(Lesson.number == 31))
                ).one()
                for mode in ("script", "guided"):
                    conversation, _ = await dialogue.create_dialogue(
                        session,
                        user,
                        lesson,
                        mode=mode,
                        operation_key=str(uuid4()),
                    )
                    for position in range(1, 13):
                        turn, job = await dialogue.admit_turn(
                            session,
                            conversation,
                            position,
                            input_kind="text",
                            transcript="I am practising today.",
                            idempotency_key=str(uuid4()),
                        )
                        assert (job is None) == (mode == "script")
                        assert turn.state == (
                            "completed" if mode == "script" else "pending"
                        )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(SkillEvidence)
                        .where(
                            SkillEvidence.user_id == user.id,
                        )
                    )
                    == 12
                )
            else:
                assert os.environ["DATABASE_PURPOSE"] == "worker"
                conversation = (
                    await session.scalars(
                        select(SpeakingDialogue)
                        .where(
                            SpeakingDialogue.mode == "guided",
                        )
                        .order_by(SpeakingDialogue.id.desc())
                        .limit(1)
                    )
                ).one()
                lesson = await dialogue.lesson_for_dialogue(
                    session, conversation.lesson_id
                )
                brief = await dialogue.brief_for_lesson(session, lesson)
                turns = (
                    await session.scalars(
                        select(DialogueTurn)
                        .where(
                            DialogueTurn.dialogue_id == conversation.id,
                        )
                        .order_by(DialogueTurn.position)
                    )
                ).all()
                assert len(turns) == 12
                for turn in turns:
                    assert turn.transcript is not None
                    await dialogue.resolve_turn(
                        session, turn, conversation, brief, turn.transcript
                    )
                    await session.refresh(turn)
                    assert turn.check_details is not None
                    assert turn.check_details["target_terms"]
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(SkillEvidence)
                        .where(
                            SkillEvidence.user_id == conversation.user_id,
                        )
                    )
                    == 24
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ReviewItem)
                        .where(
                            ReviewItem.user_id == conversation.user_id,
                            ReviewItem.origin_reason == "dialogue_missed_term",
                        )
                    )
                    == 2
                )
        print("Diálogo e evidências aprovados com papel real, sem provedor externo.")
    finally:
        assistance.call_dialogue_provider = previous_provider
        settings.assisted_features_enabled = previous_enabled
        settings.assist_dialogue_url = previous_url
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
