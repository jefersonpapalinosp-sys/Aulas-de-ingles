"""Fixture sintética para docker stop; recusa qualquer banco fora do laboratório."""

import asyncio
import sys
import time
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.models import Lesson, TranscriptionJob, User
from app.db.session import dispose_engine, get_sessionmaker
from app.db.test_safety import validate_test_target
from app.services import assistance, dialogue, transcription_queue


async def main(action: str, run_id: str) -> None:
    UUID(run_id)
    settings = get_settings()
    validate_test_target(settings.database_url, settings.app_env)
    settings.assisted_features_enabled = True
    settings.assist_provider_kind = "gateway"
    settings.assist_dialogue_url = "http://127.0.0.1:9/synthetic-never-called"
    email = f"worker-stop-{run_id}@example.test"
    try:
        if action == "run":
            async with get_sessionmaker()() as session:
                user_id = await session.scalar(select(User.id).where(User.email == email))
            if user_id is None:
                raise RuntimeError("Fixture sintética ausente")
            settings.dialogue_pilot_user_ids = [user_id]

            def reply(*args, **kwargs):
                print("S53_PROVIDER_ENTERED", flush=True)
                time.sleep(3)
                return assistance.DialogueResult(
                    raw={
                        "partner_text": "Tell me more.",
                        "hints": [],
                        "confidence": 0.9,
                    },
                    cost_microusd=7,
                    cost_known=True,
                )

            assistance.call_dialogue_provider = reply
            await transcription_queue.worker_main()
            return
        async with get_sessionmaker()() as session:
            if action == "setup":
                user = User(email=email, password_hash="synthetic", display_name="Synthetic")
                session.add(user)
                await session.flush()
                lesson = (await session.scalars(select(Lesson).where(Lesson.number == 31))).one()
                conversation, _ = await dialogue.create_dialogue(
                    session, user, lesson, mode="guided", operation_key=str(uuid4())
                )
                for position in (1, 2):
                    await dialogue.admit_turn(
                        session,
                        conversation,
                        position,
                        input_kind="text",
                        transcript="I took the train.",
                        idempotency_key=str(uuid4()),
                    )
                await session.commit()
            elif action == "check":
                rows = (
                    await session.execute(
                        select(TranscriptionJob.status, TranscriptionJob.attempt_count)
                        .join(User, User.id == TranscriptionJob.user_id)
                        .where(User.email == email)
                        .order_by(TranscriptionJob.id)
                    )
                ).all()
                assert [tuple(row) for row in rows] == [("completed", 1), ("queued", 0)], rows
                print("S53_STOP_VERIFIED: completed=1/attempt=1 queued=1/attempt=0", flush=True)
            elif action == "cleanup":
                await session.execute(delete(User).where(User.email == email))
                await session.commit()
            else:
                raise ValueError("Unknown fixture action")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:]))
