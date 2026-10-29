"""Comando de linha do seed."""

import json
from pathlib import Path

import pytest

from app import cli


def test_seed_pelo_cli(capsys: pytest.CaptureFixture[str]) -> None:
    """Síncrono de propósito: o cli chama asyncio.run(), que não pode rodar
    dentro de um loop já em andamento."""
    cli.main_com_argumentos(["seed"])
    assert "82 aulas" in capsys.readouterr().out


def test_seed_dry_run_cli(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main_com_argumentos(["seed", "--dry-run"])
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] and report["allowed"]
    assert report["changes"] == []


def test_seed_unknown_flags_never_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(**kwargs):
        pytest.fail("Must reject a mistyped flag before opening the database")

    monkeypatch.setattr(cli, "_seed", forbidden)
    for flag in ("--dryrun", "--force", "--apply"):
        with pytest.raises(SystemExit) as error:
            cli.main_com_argumentos(["seed", flag])
        assert error.value.code == 2


def test_seed_blocked_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    async def blocked(**kwargs):
        return False

    monkeypatch.setattr(cli, "_seed", blocked)
    with pytest.raises(SystemExit) as error:
        cli.main_com_argumentos(["seed", "--dry-run"])
    assert error.value.code == 1


def test_comando_desconhecido_sai_com_erro(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(["inventado"])
    assert saida.value.code == 2
    assert "uso:" in capsys.readouterr().err


def test_writing_rubrics_legado_falha_antes_de_abrir_banco(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden():
        pytest.fail("O comando desativado não pode criar sessão.")

    monkeypatch.setattr(cli, "get_sessionmaker", forbidden)
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(["writing-rubrics"])
    assert saida.value.code == 2
    assert "Use editorial-audit" in capsys.readouterr().err


def test_editorial_audit_cli_imprime_relatorio(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def audit() -> None:
        print(json.dumps({"dry_run": True, "release_ready": False}))

    monkeypatch.setattr(cli, "_editorial_audit", audit)
    cli.main_com_argumentos(["editorial-audit"])
    assert json.loads(capsys.readouterr().out) == {"dry_run": True, "release_ready": False}


def test_editorial_audit_recusa_argumento_desconhecido_antes_do_banco(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden() -> None:
        pytest.fail("Argumento inválido não pode abrir a auditoria.")

    monkeypatch.setattr(cli, "_editorial_audit", forbidden)
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(["editorial-audit", "--apply"])
    assert saida.value.code == 2


@pytest.mark.parametrize("modality", ["writing", "transcription", "conversation"])
def test_gate_assistido_falha_fechado(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, modality: str
) -> None:
    review = tmp_path / "review.json"
    review.write_text("{}", encoding="utf-8")

    async def gate(_modality: str, _review_path: Path) -> bool:
        assert _modality == modality
        assert _review_path == review
        return False

    monkeypatch.setattr(cli, "_assist_gate", gate)
    with pytest.raises(SystemExit) as saida:
        cli.main_com_argumentos(
            ["assist-gate", "--modality", modality, "--review-file", str(review)]
        )
    assert saida.value.code == 1


def test_worker_pode_processar_uma_unica_iteracao(monkeypatch: pytest.MonkeyPatch) -> None:
    chamado: list[bool] = []

    async def worker(*, once: bool = False) -> None:
        chamado.append(once)

    monkeypatch.setattr(cli, "run_transcription_worker", worker)
    cli.main_com_argumentos(["assist-worker", "--once"])

    assert chamado == [True]
