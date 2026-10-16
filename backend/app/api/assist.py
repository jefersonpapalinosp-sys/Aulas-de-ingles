"""Status, cota e custo dos experimentos assistidos."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.core.config import get_settings
from app.db.models import TranscriptionJob, WorkerHeartbeat
from app.db.session import get_session
from app.schemas.assist import AssistStatusOut
from app.services import editorial_history
from app.services.assist_quota import usage

router = APIRouter(prefix="/assist", tags=["assist"])


@router.get("/status", response_model=AssistStatusOut)
async def status_assistencia(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssistStatusOut:
    settings = get_settings()
    balance = await usage(session, usuario.id)
    enabled = settings.assisted_features_enabled
    transcription_enabled = (
        enabled
        and bool(settings.assist_transcription_url)
        and settings.editorial_snapshots_enabled
        and await editorial_history.schema_available(session)
    )
    now = datetime.now(UTC)
    seen_at = await session.scalar(
        select(WorkerHeartbeat.seen_at).where(WorkerHeartbeat.name == "transcription")
    )
    worker_state = (
        "disabled"
        if not (enabled and settings.assist_transcription_url)
        else (
            "unknown"
            if seen_at is None
            else "active"
            if seen_at >= now - timedelta(seconds=max(60, settings.assist_timeout_seconds * 2 + 20))
            else "stale"
        )
    )
    queue = (
        await session.execute(
            select(func.count(), func.min(TranscriptionJob.requested_at)).where(
                TranscriptionJob.user_id == usuario.id,
                TranscriptionJob.status == "queued",
                TranscriptionJob.expires_at > now,
            )
        )
    ).one()
    return AssistStatusOut(
        transcription_enabled=transcription_enabled,
        writing_enabled=enabled and settings.writing_assist_configured,
        daily_quota=settings.assist_daily_quota,
        used_today=balance.used,
        reserved_today=balance.reserved,
        consumed_today=balance.consumed,
        remaining_today=max(0, settings.assist_daily_quota - balance.used),
        quota_resets_at=balance.resets_at,
        retention_days=settings.assist_retention_days,
        cost_microusd_today=balance.cost,
        cost_incomplete=balance.incomplete,
        worker_state=worker_state,  # type: ignore[arg-type]
        worker_seen_at=seen_at,
        queued_jobs=queue[0],
        oldest_queued_seconds=max(0, int((now - queue[1]).total_seconds())) if queue[1] else None,
    )
