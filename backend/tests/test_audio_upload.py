"""Recepção limitada sem depender de Content-Length e contrato do proxy."""

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.core.config import Settings
from app.services import audio_upload
from app.services.audio_storage import AudioStorage


def request_for(chunks: list[bytes], declared: str | None = None) -> tuple[Request, list[int]]:
    calls: list[int] = []

    async def receive():
        index = len(calls)
        calls.append(index)
        return {"type": "http.request", "body": chunks[index], "more_body": index < len(chunks) - 1}

    headers = [] if declared is None else [(b"content-length", declared.encode())]
    return Request({"type": "http", "headers": headers}, receive), calls


@pytest.mark.asyncio
@pytest.mark.parametrize("declared", [None, "8", "1"])
async def test_stops_before_buffering_oversize_or_reading_the_tail(declared):
    request, calls = request_for([b"1234", b"56789", b"never-read"], declared)
    with pytest.raises(HTTPException) as result:
        await audio_upload.read_audio(request, 8)
    assert result.value.status_code == 413
    assert calls == [0, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("declared", ["9", "-1", "not-a-size", "1" * 30])
async def test_rejects_bad_header_before_reading(declared):
    request, calls = request_for([b"never-read"], declared)
    with pytest.raises(HTTPException) as result:
        await audio_upload.read_audio(request, 8)
    assert result.value.status_code in (400, 413)
    assert calls == []


@pytest.mark.asyncio
async def test_exact_limit_without_header_and_empty_or_truncated_body():
    request, _ = request_for([b"1234", b"5678"])
    assert await audio_upload.read_audio(request, 8) == b"12345678"
    for chunks, declared, code in (([b""], None, 422), ([b"123"], "4", 400)):
        request, _ = request_for(chunks, declared)
        with pytest.raises(HTTPException) as result:
            await audio_upload.read_audio(request, 8)
        assert result.value.status_code == code


@pytest.mark.asyncio
async def test_slow_or_disconnected_upload_does_not_produce_body(monkeypatch):
    monkeypatch.setattr(audio_upload, "UPLOAD_TIMEOUT_SECONDS", 0.01)

    async def slow():
        await asyncio.sleep(0.1)

    async def disconnect():
        return {"type": "http.disconnect"}

    for receive, code in ((slow, 408), (disconnect, 400)):
        with pytest.raises(HTTPException) as result:
            await audio_upload.read_audio(Request({"type": "http", "headers": []}, receive), 8)
        assert result.value.status_code == code


def test_api_configuration_cannot_exceed_proxy_cap():
    # O teto da borda vive em `api-proxy.conf` desde o SEC-45, compartilhado por
    # /api/ e /api/auth/. A conferência varre os dois arquivos: o que importa é
    # que o limite exista em algum lugar que as rotas da API incluam, e que ele
    # seja exatamente o do contrato — nem o nome do arquivo nem a ordem.
    raiz = Path(__file__).resolve().parents[2] / "frontend"
    borda = "\n".join(
        (raiz / nome).read_text() for nome in ("nginx.conf", "api-proxy.conf")
    )
    assert f"client_max_body_size {audio_upload.MAX_AUDIO_BYTES};" in borda
    # E as duas rotas da API precisam incluir o arquivo que carrega o teto.
    diretivas = "\n".join(
        linha
        for linha in (raiz / "nginx.conf").read_text().splitlines()
        if not linha.strip().startswith("#")
    )
    for rota in ("location /api/ {", "location /api/auth/ {"):
        bloco = diretivas.split(rota, 1)[1].split("\n    }\n", 1)[0]
        assert "include /etc/nginx/api-proxy.conf;" in bloco
    assert Settings().speaking_max_bytes == audio_upload.MAX_AUDIO_BYTES
    for limit in (0, audio_upload.MAX_AUDIO_BYTES + 1):
        with pytest.raises(ValidationError):
            Settings(speaking_max_bytes=limit)


def test_storage_retry_match_and_private_file(tmp_path):
    storage = AudioStorage(str(tmp_path))
    key = storage.save(b"bounded-synthetic-audio", "audio/webm")
    assert storage.matches(key, b"bounded-synthetic-audio")
    assert not storage.matches(key, b"another-audio")
    assert not storage.matches(None, b"anything")
    assert storage.path(key).stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("failure", [1, 2])
def test_storage_fsync_failure_never_reports_publication(tmp_path, monkeypatch, failure):
    import os

    calls = 0
    original = os.fsync

    def fail(fd):
        nonlocal calls
        calls += 1
        if calls == failure:
            raise OSError("synthetic storage failure")
        original(fd)

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        AudioStorage(str(tmp_path)).save(b"synthetic voice", "audio/wav")
    assert not list(tmp_path.glob("*.tmp"))
    # Falha após rename conserva órfão em vez de arriscar apagar publicação ambígua.
    assert len(list(tmp_path.glob("*.wav"))) == int(failure == 2)
