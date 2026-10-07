"""Comando de linha do seed."""

import pytest

from app import cli


def test_seed_pelo_cli(capsys: pytest.CaptureFixture[str]) -> None:
    """Síncrono de propósito: o cli chama asyncio.run(), que não pode rodar
    dentro de um loop já em andamento."""
    cli.main_com_argumentos(["seed"])
    assert "10 aulas" in capsys.readouterr().out


def test_comando_desconhecido_sai_com_erro(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(["inventado"])
    assert saida.value.code == 2
    assert "uso:" in capsys.readouterr().err
