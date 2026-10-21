"""Comando `worker-health`: código 0/1/2 pela idade da batida, sem expor o DSN."""

import asyncio
from collections.abc import Coroutine
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, func, update
from sqlalchemy.engine import make_url

from app import cli
from app.core.config import get_settings
from app.db.models import WorkerHeartbeat
from app.db.session import dispose_engine, get_sessionmaker
from app.services import maintenance

SEGREDOS = ("postgresql", "asyncpg", "@", "aulas_test_only")


def _run(coro: Coroutine[Any, Any, None]) -> None:
    """Síncrono de propósito, como o cli: asyncio.run() exige um loop próprio e o
    engine singleton precisa ser descartado junto com o loop que o criou."""

    async def wrapped() -> None:
        try:
            await coro
        finally:
            await dispose_engine()

    asyncio.run(wrapped())


async def _clear_heartbeat() -> None:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(delete(WorkerHeartbeat))


async def _heartbeat_with_age(age: timedelta) -> None:
    await _clear_heartbeat()
    await maintenance.heartbeat()
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(update(WorkerHeartbeat).values(seen_at=func.now() - age))


def _assert_sem_segredos(saida: pytest.CaptureFixture[str]) -> str:
    captured = saida.readouterr()
    texto = captured.out + captured.err
    for segredo in SEGREDOS:
        assert segredo not in texto, f"saída do healthcheck não pode conter {segredo!r}"
    return texto


def test_batida_fresca_sai_com_zero(capsys: pytest.CaptureFixture[str]) -> None:
    _run(_heartbeat_with_age(timedelta(0)))
    cli.main_com_argumentos(["worker-health"])  # sem SystemExit: código 0
    texto = _assert_sem_segredos(capsys)
    assert "ok" in texto and "limite 60s" in texto


def test_batida_parada_sai_com_um_e_respeita_o_limite(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _run(_heartbeat_with_age(timedelta(minutes=5)))
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(["worker-health"])
    assert saida.value.code == 1
    assert "parada" in _assert_sem_segredos(capsys)
    # A mesma linha é aceita quando o operador alarga o limite.
    cli.main_com_argumentos(["worker-health", "--max-age-seconds", "600"])


def test_sem_linha_sai_com_um(capsys: pytest.CaptureFixture[str]) -> None:
    _run(_clear_heartbeat())
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(["worker-health"])
    assert saida.value.code == 1
    assert "nenhuma batida" in _assert_sem_segredos(capsys)


def test_banco_inacessivel_sai_com_dois_sem_dsn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Conexão real recusada (porta fechada do loopback), não um mock."""
    _run(_clear_heartbeat())  # garante engine descartado antes de trocar a URL
    settings = get_settings()
    fechada = make_url(settings.database_url).set(host="127.0.0.1", port=1)
    monkeypatch.setattr(settings, "database_url", fechada.render_as_string(hide_password=False))
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(["worker-health"])
    assert saida.value.code == 2
    assert "inacessível" in _assert_sem_segredos(capsys)


def test_falha_do_helper_sai_com_dois(monkeypatch: pytest.MonkeyPatch) -> None:
    async def indisponivel() -> float | None:
        raise OSError("connection refused")

    monkeypatch.setattr(cli, "heartbeat_age_seconds", indisponivel)
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(["worker-health"])
    assert saida.value.code == 2


def test_argumentos_invalidos_falham_antes_do_banco(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(_max_age: int) -> bool:
        pytest.fail("Argumento inválido não pode abrir conexão.")

    monkeypatch.setattr(cli, "_worker_health", forbidden)
    for argumentos in (["--max-age"], ["--max-age-seconds", "0"], ["--max-age-seconds", "x"]):
        with pytest.raises(SystemExit) as saida:
            cli.main_com_argumentos(["worker-health", *argumentos])
        assert saida.value.code == 2
