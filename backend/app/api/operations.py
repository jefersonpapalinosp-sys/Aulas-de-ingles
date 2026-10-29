"""Telemetria operacional agregada e protegida, sem dados de alunos."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.health import ReadinessOut, readiness_snapshot
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas.operations import OperationsMetricsOut
from app.services import operations_metrics

router = APIRouter(prefix="/operations", tags=["operations"])
bearer = HTTPBearer(auto_error=False)


def _authorized(
    credentials: HTTPAuthorizationCredentials | None,
    settings: Settings,
) -> None:
    configured = settings.operations_token
    if not configured:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Não encontrado.")
    supplied = (
        credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    )
    if not hmac.compare_digest(supplied, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial operacional inválida.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/metrics", response_model=OperationsMetricsOut)
async def metrics(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OperationsMetricsOut:
    """Snapshot de cardinalidade fixa; nunca retorna texto, e-mail, token ou áudio."""
    _authorized(credentials, settings)
    return await operations_metrics.snapshot(session, settings)


@router.get("/readiness", response_model=ReadinessOut, responses={503: {"model": ReadinessOut}})
async def readiness(
    response: Response,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessOut:
    """Diagnóstico detalhado somente após autenticação operacional."""
    _authorized(credentials, settings)
    result = await readiness_snapshot(response, session, settings, details=True)
    response.headers["Cache-Control"] = "private, no-store"
    return result
