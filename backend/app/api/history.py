"""Private per-evidence historical content, including honest legacy absence."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.session import get_session
from app.services.editorial_history import EvidenceKind, HistoricalContentOut, get_history

router = APIRouter(tags=["history"])


@router.get("/me/history/{kind}/{evidence_id}/content", response_model=HistoricalContentOut)
async def historical_content(
    kind: EvidenceKind,
    evidence_id: Annotated[int, Path(gt=0)],
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> HistoricalContentOut:
    response.headers["Cache-Control"] = "private, no-store"
    return await get_history(session, kind, evidence_id, usuario.id)
