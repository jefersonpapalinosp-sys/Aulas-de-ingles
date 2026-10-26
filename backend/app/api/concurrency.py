"""Contrato expand/contract da Sprint 38. Não persiste conteúdo em logs."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException

from app.core.config import get_settings


def _cutover_passou() -> bool:
    return datetime.now(UTC) >= get_settings().legacy_writes_until


def require_revision(revision: int | None) -> None:
    if revision is None and _cutover_passou():
        raise HTTPException(
            428,
            detail={
                "code": "revision_required",
                "message": "Atualize a página para enviar a revisão esperada.",
            },
        )


def require_idempotency_key(key: UUID | None) -> None:
    """Escrita idempotente sem chave, depois do cutover, tem código próprio.

    Antes isso reaproveitava ``revision_required``, o que mandava o cliente
    procurar uma revisão que ele já havia enviado: o que falta é a chave.
    """
    if key is None and _cutover_passou():
        raise HTTPException(
            428,
            detail={
                "code": "idempotency_key_required",
                "message": "Atualize a página para enviar a chave de idempotência.",
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
