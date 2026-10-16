"""Lotes fixos, canceláveis entre transações, sem acesso aos arquivos de áudio."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.db.models import WorkerHeartbeat
from app.db.session import get_sessionmaker

SCOPES = ("transcriptions", "reservations", "refresh", "pending")


async def retention_batch(kind: str, *, apply: bool = False, limit: int = 100) -> int:
    if kind not in SCOPES or not 1 <= limit <= 500:
        raise ValueError("Escopo/limite inválido.")
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(text("SET LOCAL statement_timeout = '5s'"))
        await session.execute(text("SET LOCAL lock_timeout = '1s'"))
        result = await session.scalar(
            text("SELECT public.aulas_retention_batch(:kind, :limit, :apply)"),
            {"kind": kind, "limit": limit, "apply": apply},
        )
        return int(result or 0)


async def sweep() -> dict[str, int]:
    settings = get_settings()
    scopes = SCOPES if settings.maintenance_cleanup_enabled else SCOPES[:2]
    return {
        scope: await retention_batch(scope, apply=True, limit=settings.maintenance_batch_size)
        for scope in scopes
    }


async def heartbeat(counts: dict[str, int] | None = None) -> None:
    async with get_sessionmaker()() as session, session.begin():
        values: dict[str, Any] = {"name": "transcription", "seen_at": func.now()}
        if counts is not None:
            values.update(maintenance_at=datetime.now(UTC), maintenance_counts=counts)
        statement = insert(WorkerHeartbeat).values(**values)
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[WorkerHeartbeat.name],
                set_={k: v for k, v in values.items() if k != "name"},
            )
        )
