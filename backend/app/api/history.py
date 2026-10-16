"""Private per-evidence historical content, including honest legacy absence."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.session import get_session
from app.pagination import InvalidCursor, decode_time_id_cursor
from app.services.editorial_history import (
    EvidenceKind,
    HistoricalContentOut,
    HistoricalEvidencePageOut,
    get_history,
    history_page,
)

router = APIRouter(tags=["history"])


@router.get("/me/history/page", response_model=HistoricalEvidencePageOut)
async def historical_evidence_page(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> HistoricalEvidencePageOut:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        boundary = decode_time_id_cursor(cursor) if cursor is not None else None
    except InvalidCursor as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_cursor", "message": "Cursor de paginação inválido."},
        ) from error
    return await history_page(session, usuario.id, limit, boundary)


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
