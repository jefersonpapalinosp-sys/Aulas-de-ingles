"""Contrato expand/contract da Sprint 38. Não persiste conteúdo em logs."""

from datetime import UTC, datetime

from fastapi import HTTPException

from app.core.config import get_settings


def require_revision(revision: int | None) -> None:
    if revision is None and datetime.now(UTC) >= get_settings().legacy_writes_until:
        raise HTTPException(
            428,
            detail={
                "code": "revision_required",
                "message": "Atualize a página para enviar a revisão esperada.",
            },
        )


def conflict(code: str, current: dict[str, object]) -> HTTPException:
    return HTTPException(
        409,
        detail={
            "code": code,
            "message": "O estado mudou em outra sessão. Confira antes de reenviar.",
            "current": current,
        },
    )
