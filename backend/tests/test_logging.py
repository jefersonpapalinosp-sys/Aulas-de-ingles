"""Log estruturado e request-id."""

import json
import logging

import pytest
from httpx import AsyncClient

from app.core.logging import CABECALHO, FormatadorJson, request_id_atual


def test_formatador_produz_json_com_os_campos_extra() -> None:
    registro = logging.LogRecord("app.teste", logging.INFO, "f.py", 1, "oi %s", ("mundo",), None)
    registro.status = 200
    saida = json.loads(FormatadorJson().format(registro))
    assert saida["msg"] == "oi mundo"
    assert saida["level"] == "INFO"
    assert saida["logger"] == "app.teste"
    assert saida["status"] == 200
    assert saida["ts"].endswith("Z")


def test_formatador_inclui_traceback() -> None:
    try:
        raise ValueError("quebrou")
    except ValueError:
        registro = logging.LogRecord("x", logging.ERROR, "f.py", 1, "falhou", (), None)
        import sys

        registro.exc_info = sys.exc_info()
    saida = json.loads(FormatadorJson().format(registro))
    assert "ValueError: quebrou" in saida["exception"]


def test_request_id_entra_no_json() -> None:
    token = request_id_atual.set("abc123")
    registro = logging.LogRecord("x", logging.INFO, "f.py", 1, "oi", (), None)
    assert json.loads(FormatadorJson().format(registro))["request_id"] == "abc123"
    request_id_atual.reset(token)


@pytest.mark.asyncio
async def test_resposta_devolve_request_id(client: AsyncClient) -> None:
    r = await client.get("/api/live")
    assert r.headers[CABECALHO]
    assert len(r.headers[CABECALHO]) == 16


@pytest.mark.asyncio
async def test_request_id_de_fora_e_respeitado(client: AsyncClient) -> None:
    """Com um proxy na frente, é o id dele que amarra o rastro de ponta a ponta."""
    r = await client.get("/api/live", headers={CABECALHO: "veio-de-fora"})
    assert r.headers[CABECALHO] == "veio-de-fora"


@pytest.mark.asyncio
async def test_requisicao_vira_uma_linha_de_log(client: AsyncClient, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="app.request"):
        await client.get("/api/live")
    registro = next(r for r in caplog.records if r.name == "app.request")
    assert registro.status == 200
    assert registro.path == "/api/live"
    assert registro.duration_ms >= 0
