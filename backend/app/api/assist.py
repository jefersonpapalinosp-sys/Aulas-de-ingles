"""Status, cota e custo dos experimentos assistidos."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.core.config import get_settings
from app.db.models import TranscriptionJob, WritingFeedbackRecord
from app.db.session import get_session
from app.schemas.assist import AssistStatusOut

router = APIRouter(prefix="/assist", tags=["assist"])


async def assisted_usage(session: AsyncSession, user_id: int) -> tuple[int, int]:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    transcription = (
        await session.execute(
            select(
                func.count(TranscriptionJob.id),
                func.coalesce(func.sum(TranscriptionJob.cost_microusd), 0),
            ).where(TranscriptionJob.user_id == user_id, TranscriptionJob.requested_at >= start)
        )
    ).one()
    writing = (
        await session.execute(
            select(
                func.count(WritingFeedbackRecord.id),
                func.coalesce(func.sum(WritingFeedbackRecord.assisted_cost_microusd), 0),
            ).where(
                WritingFeedbackRecord.user_id == user_id,
                WritingFeedbackRecord.provider.is_not(None),
                WritingFeedbackRecord.created_at >= start,
            )
        )
    ).one()
    return int(transcription[0] + writing[0]), int(transcription[1] + writing[1])


@router.get("/status", response_model=AssistStatusOut)
async def status_assistencia(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssistStatusOut:
    settings = get_settings()
    used, cost = await assisted_usage(session, usuario.id)
    enabled = settings.assisted_features_enabled
    return AssistStatusOut(
        transcription_enabled=enabled and bool(settings.assist_transcription_url),
        writing_enabled=enabled and settings.writing_assist_configured,
        daily_quota=settings.assist_daily_quota,
        used_today=used,
        remaining_today=max(0, settings.assist_daily_quota - used),
        retention_days=settings.assist_retention_days,
        cost_microusd_today=cost,
    )
