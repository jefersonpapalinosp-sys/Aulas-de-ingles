"""Comando de linha do seed."""

from pathlib import Path

import pytest

from app import cli


def test_seed_pelo_cli(capsys: pytest.CaptureFixture[str]) -> None:
    """Síncrono de propósito: o cli chama asyncio.run(), que não pode rodar
    dentro de um loop já em andamento."""
    cli.main_com_argumentos(["seed"])
    assert "37 aulas" in capsys.readouterr().out


def test_comando_desconhecido_sai_com_erro(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(["inventado"])
    assert saida.value.code == 2
    assert "uso:" in capsys.readouterr().err


def test_gate_assistido_falha_fechado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    review = tmp_path / "review.json"
    review.write_text("{}", encoding="utf-8")

    async def gate(_modality: str, _review_path: Path) -> bool:
        return False

    monkeypatch.setattr(cli, "_assist_gate", gate)
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(
            ["assist-gate", "--modality", "writing", "--review-file", str(review)]
        )
    assert saida.value.code == 1


def test_worker_pode_processar_uma_unica_iteracao(monkeypatch: pytest.MonkeyPatch) -> None:
    chamado: list[bool] = []

    async def worker(*, once: bool = False) -> None:
        chamado.append(once)

    monkeypatch.setattr(cli, "run_transcription_worker", worker)
    cli.main_com_argumentos(["assist-worker", "--once"])

    assert chamado == [True]
