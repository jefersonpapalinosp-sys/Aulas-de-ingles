"""Limita bytes e tempo de recepção; não atesta codec nem duração decodificada."""

import asyncio

from fastapi import HTTPException, Request
from starlette.requests import ClientDisconnect

MAX_AUDIO_BYTES = 2_000_000  # Mesmo teto em frontend/nginx.conf; MB decimal.
MAX_DURATION_MS = 30_000  # Contrato existente e constraint do banco.
UPLOAD_TIMEOUT_SECONDS = 30


async def read_audio(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None:
        if not declared.isascii() or not declared.isdigit() or len(declared) > 20:
            raise HTTPException(400, "Tamanho declarado inválido.")
        if int(declared) > limit:
            raise HTTPException(413, f"Áudio excede o limite de {limit} bytes.")
    body = bytearray()
    try:
        async with asyncio.timeout(UPLOAD_TIMEOUT_SECONDS):
            async for chunk in request.stream():
                # Conferir ANTES de copiar: também vale sem Content-Length ou se ele mentir.
                if len(body) + len(chunk) > limit:
                    raise HTTPException(413, f"Áudio excede o limite de {limit} bytes.")
                body.extend(chunk)
    except TimeoutError:
        raise HTTPException(
            408, "O envio demorou demais. Tente novamente com o mesmo áudio."
        ) from None
    except ClientDisconnect:
        raise HTTPException(400, "Envio interrompido; tente novamente.") from None
    if declared is not None and int(declared) != len(body):
        raise HTTPException(400, "Tamanho recebido difere do declarado.")
    if not body:
        raise HTTPException(422, "Áudio vazio.")
    return bytes(body)
