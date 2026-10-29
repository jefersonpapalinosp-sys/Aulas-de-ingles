"""INFRA-48: backup/restore sintético em projeto fixo, sem tocar laboratórios anteriores."""

import argparse
import json
import os
from typing import TypedDict

from ops import recovery as r
from ops.recovery_archive import RecoveryError, require, write_json

COMPOSE = [
    "compose",
    "--env-file",
    str(r.ROOT / "infra/e2e.env"),
    "-p",
    r.DIALOGUE_PROJECT,
    "-f",
    str(r.ROOT / "infra/compose.recovery48.yml"),
]
TABLES = ("speaking_dialogue", "dialogue_turn", "assist_reservation", "transcription_job")


def resources() -> None:
    r.local_daemon()
    existing = set(r.docker("volume", "ls", "--format", "{{.Name}}").decode().splitlines())
    for target in (r.DIALOGUE_LAB, r.DIALOGUE_RESTORE):
        for name in (target.db_volume, target.voice_volume):
            if name in existing:
                r.volume(name, r.DIALOGUE_PROJECT, True)
    network_name = f"{r.DIALOGUE_PROJECT}_default"
    networks = r.docker("network", "ls", "--format", "{{.Name}}").decode().splitlines()
    if network_name in networks:
        network = json.loads(r.docker("network", "inspect", network_name))[0]
        require(
            network["Internal"]
            and network["Driver"] == "bridge"
            and network["Labels"].get("com.docker.compose.project") == r.DIALOGUE_PROJECT,
            "Rede do laboratório precisa ser interna e exclusiva.",
        )


class Fingerprint(TypedDict):
    count: int
    digest: str


def fingerprints(target: r.Target) -> dict[str, Fingerprint]:
    # Tabelas fixas; só hashes e contagens saem do banco, nunca texto.
    result: dict[str, Fingerprint] = {}
    for table in TABLES:
        value = r.query(
            target,
            f"SELECT json_build_object('count',count(*),'digest',"
            f"md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY id)::text,'[]'))) FROM public.{table} t",
        )
        if not isinstance(value, dict):
            raise RecoveryError("Fingerprint de tabela inválido.")
        count, digest = value.get("count"), value.get("digest")
        if type(count) is not int or count < 0 or not isinstance(digest, str):
            raise RecoveryError("Fingerprint de tabela inválido.")
        result[table] = {"count": count, "digest": digest}
    return result


def application_read() -> dict[str, object]:
    result: object = json.loads(
        r.docker(
            "run",
            "--rm",
            "--network",
            f"{r.DIALOGUE_PROJECT}_default",
            "--user",
            "10001:10001",
            "--entrypoint",
            "python",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-e",
            "APP_ENV=dev",
            "-e",
            "DIALOGUE_RECOVERY_ONLY=disposable-recovery48",
            "-e",
            "DATABASE_URL=postgresql+asyncpg://aulas_restore:restore_disposable_only@target-db:5432/aulas_ingles_restore",
            "-e",
            "SPEAKING_STORAGE_DIR=/app/data/speaking",
            "--mount",
            f"type=volume,src={r.DIALOGUE_RESTORE.voice_volume},dst=/app/data/speaking,readonly",
            "--mount",
            f"type=bind,src={r.ROOT / 'ops'},dst=/tools,readonly",
            r.HELPER,
            "/tools/dialogue_recovery_data.py",
            "check",
            timeout=120,
        )
    )

    if not isinstance(result, dict):
        raise RecoveryError("Resposta de leitura da aplicação inválida.")
    return result


def check() -> None:
    r.check_target(r.DIALOGUE_LAB)
    r.check_target(r.DIALOGUE_RESTORE)
    require(
        r.query(r.DIALOGUE_RESTORE, r.EMPTY_SQL) == 0,
        "Destino já ocupado; preservar recibos e volumes existentes.",
    )
    require(
        r.query(
            r.DIALOGUE_LAB,
            "SELECT to_json(count(*)=1 AND bool_and(email='recovery-synthetic@example.invalid')) "
            "FROM public.app_user",
        )
        is True,
        "Origem precisa conter apenas a conta sintética.",
    )
    before = fingerprints(r.DIALOGUE_LAB)
    require(
        [before[t]["count"] for t in TABLES] == [1, 2, 2, 3],
        "Fixture sintética de conversa incompleta.",
    )
    bundle = r.backup("dialogue-lab")
    receipt = r.restore(bundle, r.CONFIRM_DIALOGUE)
    require(fingerprints(r.DIALOGUE_RESTORE) == before, "Conversa restaurada divergente.")
    app = application_read()
    require(app.get("verified") is True, "Aplicação não confirmou a leitura.")
    require(fingerprints(r.DIALOGUE_LAB) == before, "Origem alterada.")
    require(fingerprints(r.DIALOGUE_RESTORE) == before, "Leitura alterou o destino.")
    proof = receipt.with_name(receipt.stem + "-conversation.json")
    result = {
        "verified": True,
        "synthetic_only": True,
        "bundle": str(bundle),
        "restore_receipt": str(receipt),
        "application_read": app,
        "tables": before,
    }
    write_json(proof, result)
    print(json.dumps({**result, "conversation_receipt": str(proof)}, indent=2))


def main(argv: list[str] | None = None) -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("up", "prepare", "check", "down"))
    args = parser.parse_args(argv)
    resources()
    if args.command == "up":
        r.docker(
            "build",
            "-f",
            str(r.ROOT / "backend/Dockerfile.prod"),
            "-t",
            r.HELPER,
            str(r.ROOT),
            timeout=600,
        )
        r.docker(*COMPOSE, "up", "-d", "--wait", "--wait-timeout", "120", timeout=180)
        resources()
    elif args.command == "prepare":
        r.check_target(r.DIALOGUE_LAB)
        with r.lease("recovery48-prepare"):
            r._prepare_empty_lab(r.DIALOGUE_LAB)
    elif args.command == "check":
        check()
    else:
        r.docker(*COMPOSE, "down", timeout=120)  # Sem -v: preservar evidências.


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Ensaio INFRA-48 falhou; preserve os volumes e pacotes para diagnóstico.")
        raise SystemExit(1) from None
