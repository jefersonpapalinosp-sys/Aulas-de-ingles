"""Decodificação fora do event loop/SQL, com concorrência e recursos limitados."""

import asyncio
import json
import os
import sys
from contextlib import suppress
from pathlib import Path

from fastapi import HTTPException

from app.services.audio_upload import MAX_AUDIO_BYTES, MAX_DURATION_MS

INSPECTION_TIMEOUT = 8
MAX_INSPECTIONS = 2  # Por processo API, não um limite global entre réplicas.
_active = 0
WORKER = Path(__file__).with_name("audio_probe_worker.py")


def unavailable() -> HTTPException:
    return HTTPException(
        503, "Verificação de áudio indisponível. Tente novamente.", headers={"Retry-After": "2"}
    )


async def inspect_audio(data: bytes, mime: str) -> int:
    global _active
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Áudio excede o limite de bytes.")
    if _active >= MAX_INSPECTIONS:
        raise unavailable()
    _active += 1
    process = None
    tasks: list[asyncio.Task[object]] = []
    try:
        async with asyncio.timeout(INSPECTION_TIMEOUT):
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                str(WORKER),
                mime,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={"PATH": os.defpath, "LC_ALL": "C"},
                limit=4096,
            )
            assert process.stdin is not None and process.stdout is not None
            stdin, stdout = process.stdin, process.stdout

            async def feed() -> object:
                try:
                    stdin.write(data)
                    await stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    stdin.close()
                return None

            async def read() -> object:
                output = bytearray()
                while chunk := await stdout.read(1024):
                    output.extend(chunk)
                    if len(output) > 4096:
                        raise unavailable()
                return bytes(output)

            tasks = [asyncio.create_task(feed()), asyncio.create_task(read())]
            _, raw = await asyncio.gather(*tasks)
            if await process.wait() != 0:
                raise unavailable()
        assert isinstance(raw, bytes)
        result = json.loads(raw)
        if result.get("error") == "unavailable":
            raise unavailable()
        if result.get("error") == "unsupported":
            raise HTTPException(415, "Formato/codec real não corresponde ao áudio permitido.")
        if result.get("error") == "too_long":
            raise HTTPException(
                422, "A duração real excede 30 segundos. Grave um trecho mais curto."
            )
        duration = result.get("duration_ms")
        if type(duration) is not int or not 1 <= duration <= MAX_DURATION_MS:
            raise HTTPException(422, "Áudio inválido, vazio ou não decodificável. Grave novamente.")
        return duration
    except (TimeoutError, OSError, ValueError, AttributeError):
        raise unavailable() from None
    finally:
        if process is not None and process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if process is not None:
            # Drenar sem acumular após kill: wait() sozinho pode bloquear com pipe cheio.
            if process.stdout is not None:
                while await process.stdout.read(65536):
                    pass
            await process.wait()
        _active -= 1
