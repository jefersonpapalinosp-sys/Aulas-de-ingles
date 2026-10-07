"""Health check: liveness simples e readiness que de fato toca o banco."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session

log = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: str
    db: str
    version: str | None = None
    env: str


@router.get("/health", response_model=HealthOut)
async def health(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthOut:
    """Readiness.

    Abre uma conexão de verdade e pergunta a versão ao Postgres. Se o banco
    não responder, devolve 503 — é isso que faz o healthcheck valer alguma coisa.
    """
    try:
        result = await session.execute(text("select version()"))
        raw = result.scalar_one()
        # "PostgreSQL 16.4 (Debian ...) on aarch64..." -> "PostgreSQL 16.4"
        version = " ".join(str(raw).split()[:2])
    except Exception:
        log.exception("health: banco indisponível")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthOut(status="degraded", db="down", version=None, env=settings.app_env)

    return HealthOut(status="ok", db="up", version=version, env=settings.app_env)


@router.get("/live")
async def live() -> dict[str, str]:
    """Liveness: o processo está de pé. Não toca em dependência nenhuma."""
    return {"status": "ok"}
