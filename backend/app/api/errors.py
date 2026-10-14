"""Contrato aditivo de erros: mantém detail legado, sem SQL/credenciais nas respostas."""

import logging
from collections.abc import Mapping
from typing import Any, Literal

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException

from app.core.logging import request_id_atual

ErrorCode = Literal["session_invalid", "invalid_credentials", "conflict", "service_unavailable"]


class ApiErrorOut(BaseModel):
    code: ErrorCode
    detail: str | dict[str, object]
    request_id: str


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ApiErrorOut, "description": description}
    for code, description in (
        (401, "Sessão inválida ou credenciais recusadas; não repetir indefinidamente."),
        (409, "Conflito; preservar o trabalho e conferir o estado antes de reenviar."),
        (503, "Indisponibilidade; preservar o trabalho. Não implica sessão revogada."),
    )
}


def response(
    code: ErrorCode,
    status: int,
    detail: str | dict[str, object],
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    payload = ApiErrorOut(code=code, detail=detail, request_id=request_id_atual.get())
    return JSONResponse(
        status_code=status,
        content=payload.model_dump(),
        headers={**(headers or {}), "X-Error-Code": code, "Cache-Control": "no-store"},
    )


async def http_error(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, HTTPException)
    if exc.status_code not in (401, 409, 503):
        return await http_exception_handler(request, exc)
    code: ErrorCode = "conflict" if exc.status_code == 409 else "service_unavailable"
    if exc.status_code == 401:
        code = "invalid_credentials" if request.url.path == "/api/auth/login" else "session_invalid"
    # Detalhes são literais/estruturas controlados pelas rotas, nunca repr(exc).
    return response(code, exc.status_code, exc.detail, exc.headers)


async def unavailable(request: Request, exc: Exception) -> JSONResponse:
    # Não logar SQL, parâmetros, corpos nem a mensagem da exceção de transporte.
    logging.getLogger(__name__).warning(
        "dependência indisponível", extra={"error_type": type(exc).__name__}
    )
    return response(
        "service_unavailable",
        503,
        "Serviço temporariamente indisponível. Preserve seu trabalho e tente novamente.",
    )


async def database_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DBAPIError)
    sqlstate = getattr(exc.orig, "sqlstate", None)
    if sqlstate in {"40P01", "40001", "55P03"}:
        # A transação será revertida pela sessão. Sem retry automático ilimitado.
        return await unavailable(request, exc)
    if sqlstate == "23505":
        return response(
            "conflict", 409, "Registro concorrente. Confira o estado antes de reenviar."
        )
    logging.getLogger(__name__).error(
        "falha SQL não classificada", extra={"error_type": type(exc).__name__}
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Falha interna ao persistir dados."},
        headers={"Cache-Control": "no-store"},
    )
