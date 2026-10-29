"""SEC-49: rotação exclusivamente em laboratório fixo, sem aceitar alvo externo."""

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ops import recovery
from ops.recovery_archive import RecoveryError, file_info, require, write_json

PROJECT = "aulas-ingles-rotation49"
VOLUME = f"{PROJECT}_pgdata"
NETWORK = f"{PROJECT}_default"
MARKER = "disposable-rotation49"
PROBE_NAME = f"{PROJECT}-probe"
COMPOSE = [
    "compose",
    "--env-file",
    "infra/e2e.env",
    "-p",
    PROJECT,
    "-f",
    "infra/compose.rotation.yml",
]


def validate_network(value: dict[str, Any]) -> None:
    labels = value.get("Labels") or {}
    require(
        value.get("Name") == NETWORK
        and value.get("Driver") == "bridge"
        and value.get("Internal") is True
        and labels.get("com.docker.compose.project") == PROJECT,
        "Rede de rotação não é interna e exclusiva.",
    )


def resources() -> None:
    recovery.local_daemon()
    volumes = recovery.docker("volume", "ls", "--format", "{{.Name}}").decode().splitlines()
    if VOLUME in volumes:
        value = json.loads(recovery.docker("volume", "inspect", VOLUME))[0]
        recovery.validate_volume(value, PROJECT, VOLUME, False)
        require(
            (value.get("Labels") or {}).get("org.aulas.environment") == MARKER,
            "Volume sem marcador exclusivo SEC-49.",
        )
    networks = recovery.docker("network", "ls", "--format", "{{.Name}}").decode().splitlines()
    if NETWORK in networks:
        validate_network(json.loads(recovery.docker("network", "inspect", NETWORK))[0])


def validate_container(info: dict[str, Any]) -> None:
    require(
        info["State"]["Running"]
        and not info["HostConfig"]["Privileged"]
        and not info["HostConfig"].get("PortBindings")
        and info["Config"]["Image"] == recovery.POSTGRES
        and set(info["NetworkSettings"]["Networks"]) == {NETWORK},
        "Container de rotação fora da topologia descartável.",
    )
    mounts = info["Mounts"]
    require(
        len(mounts) == 2
        and any(
            m.get("Name") == VOLUME and m["Destination"] == "/var/lib/postgresql/data"
            for m in mounts
        )
        and any(
            m["Type"] == "bind"
            and not m["RW"]
            and recovery.expected_bind_source(
                m["Source"], recovery.ROOT / "infra/rotation-db-init.sql"
            )
            and m["Destination"] == "/docker-entrypoint-initdb.d/01-rotation.sql"
            for m in mounts
        ),
        "Mounts de rotação não correspondem ao laboratório.",
    )


def receipt_root() -> Path:
    root = recovery.BACKUPS
    require(not root.is_symlink() and not root.parent.is_symlink(), "Recibos redirecionados.")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(root.stat().st_mode & 0o077 == 0, "Diretório de recibos não é privado.")
    return root


def run_probe() -> dict[str, object]:
    resources()
    validate_container(recovery.container(PROJECT, "db"))
    root = receipt_root()
    # Nome fixo impede concorrência. Só removemos o ID que create devolveu;
    # container preexistente é recusado, nunca removido para abrir espaço.
    container_id = (
        recovery.docker(
            "create",
            "--name",
            PROBE_NAME,
            "--network",
            NETWORK,
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=64m",
            "--user",
            "10001:10001",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--entrypoint",
            "python",
            "-e",
            f"ROTATION_LAB={MARKER}",
            "-e",
            "APP_ENV=dev",
            "--mount",
            f"type=bind,src={recovery.ROOT / 'ops'},dst=/app/ops,readonly",
            recovery.HELPER,
            "-m",
            "ops.rotation_probe",
        )
        .decode()
        .strip()
    )
    require(
        len(container_id) == 64 and all(c in "0123456789abcdef" for c in container_id),
        "ID do container de sonda inválido.",
    )
    try:
        result = recovery.docker("start", "--attach", container_id, timeout=300)
    except RecoveryError as error:
        diagnostic = getattr(error.__cause__, "stderr", b"")
        if isinstance(diagnostic, bytes):
            match = re.search(
                rb"^SEC-49: fase=(preflight|prepare|initial_session|password_rotation|"
                rb"stale_consumer|jwt_rotation|provider_rotation); tipo=([A-Za-z]{1,48})$",
                diagnostic,
                re.MULTILINE,
            )
            if match:
                print(match.group().decode(), file=sys.stderr)
        raise
    finally:
        recovery.docker("rm", "-f", container_id)
    report: object = json.loads(result)
    require(isinstance(report, dict), "Recibo de rotação inválido.")
    # Somente campos agregados podem sair do laboratório; nenhuma credencial.
    from ops.rotation_probe import validate_report

    validated = validate_report(report)
    payload: dict[str, object] = {
        "verified": True,
        "laboratory": PROJECT,
        "result": validated,
        "scripts": {
            name: file_info(recovery.ROOT / "ops" / name)
            for name in (
                "rotation_rehearsal.py",
                "rotation_probe.py",
                "rotation_provider.py",
            )
        },
    }
    name = f"rotation49-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}.json"
    write_json(root / name, payload)
    return payload


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "check", "down"])
    action = parser.parse_args().action
    resources()
    if action == "up":
        recovery.docker(
            "build", "-f", "backend/Dockerfile.prod", "-t", recovery.HELPER, ".", timeout=900
        )
        recovery.docker(*COMPOSE, "up", "-d", "--wait", "--wait-timeout", "120", timeout=180)
        validate_container(recovery.container(PROJECT, "db"))
    elif action == "check":
        print(json.dumps(run_probe(), sort_keys=True))
    else:
        recovery.docker(*COMPOSE, "down", timeout=120)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Ensaio SEC-49 recusado; preserve o laboratório para diagnóstico.", file=sys.stderr)
        raise SystemExit(1) from None
