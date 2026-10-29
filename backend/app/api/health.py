"""Liveness independente e readiness que valida banco e revisão de schema."""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session

log = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    db: str
    schema_status: Literal["compatible", "incompatible", "unknown"] = Field(alias="schema")
    code: Literal["service_unavailable", "schema_incompatible"] | None = None


class ReadinessOut(HealthOut):
    version: str | None = None
    schema_current: list[str]
    schema_required: list[str]
    env: str


@lru_cache(maxsize=1)
def required_schema_heads() -> tuple[str, ...]:
    """Retorna os heads embarcados na mesma imagem da API.

    O caminho absoluto evita depender do diretório corrente do processo. A
    imagem de produção leva ``alembic.ini`` e ``alembic/`` junto com o código.
    """
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


async def current_schema_heads(session: AsyncSession) -> tuple[str, ...]:
    result = await session.execute(text("SELECT version_num FROM alembic_version"))
    return tuple(sorted(str(value) for value in result.scalars().all()))


@router.get("/health", response_model=HealthOut, responses={503: {"model": HealthOut}})
async def health(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthOut:
    """Disponibilidade pública, sem versão do banco, ambiente ou revisões."""
    result = await readiness_snapshot(response, session, settings)
    return HealthOut(
        status=result.status, db=result.db, schema=result.schema_status, code=result.code
    )


async def readiness_snapshot(
    response: Response, session: AsyncSession, settings: Settings, *, details: bool = False
) -> ReadinessOut:
    """Readiness.

    Abre uma conexão de verdade e exige que a revisão aplicada seja exatamente
    o conjunto de heads embarcado. Banco acessível com código/schema divergentes
    continua indisponível para tráfego.
    """
    response.headers["Cache-Control"] = "no-store"
    try:
        result = await session.execute(text("select version()" if details else "SELECT 1"))
        raw = result.scalar_one()
        # "PostgreSQL 16.4 (Debian ...) on aarch64..." -> "PostgreSQL 16.4"
        version = " ".join(str(raw).split()[:2]) if details else None
    except Exception:
        log.warning("health: banco indisponível")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        response.headers["X-Error-Code"] = "service_unavailable"
        response.headers["Cache-Control"] = "no-store"
        return ReadinessOut(
            status="degraded",
            db="down",
            version=None,
            schema="unknown",
            schema_current=[],
            schema_required=list(required_schema_heads()),
            env=settings.app_env,
            code="service_unavailable",
        )

    required = required_schema_heads()
    try:
        current = await current_schema_heads(session)
    except Exception as exc:
        # A conexão já foi comprovada acima. Tabela ausente, permissão incorreta
        # ou catálogo ilegível são incompatibilidade de schema, não banco "down".
        log.warning(
            "health: schema indisponível",
            extra={"error_type": type(exc).__name__},
        )
        current = ()
    if current != required:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        response.headers["X-Error-Code"] = "schema_incompatible"
        response.headers["Cache-Control"] = "no-store"
        return ReadinessOut(
            status="degraded",
            db="up",
            version=version,
            schema="incompatible",
            schema_current=list(current),
            schema_required=list(required),
            env=settings.app_env,
            code="schema_incompatible",
        )

    return ReadinessOut(
        status="ok",
        db="up",
        version=version,
        schema="compatible",
        schema_current=list(current),
        schema_required=list(required),
        env=settings.app_env,
    )


@router.get("/live")
async def live() -> dict[str, str]:
    """Liveness: o processo está de pé. Não toca em dependência nenhuma."""
    return {"status": "ok"}
