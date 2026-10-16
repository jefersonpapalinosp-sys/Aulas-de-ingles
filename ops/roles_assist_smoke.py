"""Executa serviços de cota com os papéis reais, apenas no laboratório sintético."""

import asyncio
import os
from uuid import uuid4

from app.db.models import AssistReservation, User
from app.db.session import dispose_engine, get_sessionmaker
from app.services import assist_quota
from sqlalchemy import select

assert os.environ["DATABASE_URL"].endswith("@db:5432/aulas_roles_lab")


async def main():
    try:
        async with get_sessionmaker()() as session, session.begin():
            if os.environ["DATABASE_PURPOSE"] == "runtime":
                user_id = await session.scalar(
                    select(User.id).order_by(User.id.desc()).limit(1)
                )
                assert user_id is not None
                writing, created = await assist_quota.reserve(
                    session, user_id, f"roles-writing-{uuid4().hex}", "hash", "writing"
                )
                assert created and await assist_quota.consume(session, writing.id)
                await assist_quota.record_cost(session, writing.id, 1)
                await assist_quota.reserve(
                    session,
                    user_id,
                    f"roles-queue-{uuid4().hex}",
                    "hash",
                    "transcription",
                )
            else:
                assert os.environ["DATABASE_PURPOSE"] == "worker"
                row = await session.scalar(
                    select(AssistReservation)
                    .where(
                        AssistReservation.request_key.like("roles-queue-%"),
                        AssistReservation.state == "reserved",
                    )
                    .order_by(AssistReservation.id.desc())
                    .limit(1)
                )
                assert row is not None and await assist_quota.consume(session, row.id)
                await assist_quota.record_cost(session, row.id, 2)
        print(
            "Serviço de cotas aprovado no papel do laboratório, sem provedor externo."
        )
    finally:
        await dispose_engine()


asyncio.run(main())
