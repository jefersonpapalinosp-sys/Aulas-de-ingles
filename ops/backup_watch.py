"""Agendamento sem chave privada e status agregado após cópia externa verificada."""

import argparse
import contextlib
import io
import json
import os
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ops import public_backup
from ops.recovery_archive import RecoveryError, require


def save_status(path: Path, value: dict[str, Any]) -> None:
    require(not path.is_symlink() and not path.parent.is_symlink(), "Status não pode ser link.")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".backup-status-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_status(path: Path) -> dict[str, Any]:
    require(
        path.is_file() and not path.is_symlink() and path.stat().st_size <= 4096,
        "Status de backup ausente ou inválido.",
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RecoveryError("Status de backup inválido.")
    return value


def freshness(path: Path, now: datetime | None = None) -> tuple[bool, float | None]:
    now = now or datetime.now(UTC)
    try:
        value = read_status(path)
        stamp = datetime.fromisoformat(value["last_success_at"])
        require(stamp.tzinfo is not None, "Data sem fuso.")
        age = (now - stamp).total_seconds() / 3600
        return value.get("last_attempt_ok") is True and 0 <= age <= 24, round(age, 3)
    except (OSError, ValueError, KeyError, TypeError, RecoveryError):
        return False, None


def run(status: Path, *, host: str, recipient: Path, encrypted: Path, external: Path) -> int:
    started = datetime.now(UTC).isoformat()
    last_success = None
    if status.exists():
        with contextlib.suppress(OSError, ValueError, RecoveryError):
            last_success = read_status(status).get("last_success_at")
    state = {"last_attempt_at": started, "last_success_at": last_success, "last_attempt_ok": False}
    # Crash/timeout após iniciar já deixa o gate vermelho, sem esperar 24 horas.
    save_status(status, state)
    require(external.is_dir() and not external.is_symlink(), "Destino externo ausente.")
    require(external.resolve() != encrypted.resolve(), "Cópia externa deve ter destino separado.")
    with contextlib.redirect_stdout(io.StringIO()):
        result = public_backup.main(
            [
                "--host",
                host,
                "capture",
                "--recipient-file",
                str(recipient),
                "--encrypted-dir",
                str(encrypted),
                "--copy-to",
                str(external),
                "--json",
            ]
        )
    if result == 0:
        save_status(
            status,
            {**state, "last_success_at": datetime.now(UTC).isoformat(), "last_attempt_ok": True},
        )
        print("Backup cifrado e cópia externa verificados.")
    else:
        print("ALERTA: backup falhou; conferir o gate e preservar parciais.")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--host", default="local")
    parser.add_argument("--recipient-file", type=Path, required=True)
    parser.add_argument("--encrypted-dir", type=Path, required=True)
    parser.add_argument("--copy-to", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # flock é liberado pelo kernel mesmo após SIGKILL; runner Linux.
        import fcntl

        args.status.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock = args.status.with_suffix(".lock")
        require(not lock.is_symlink(), "Lock não pode ser link.")
        with lock.open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return run(
                args.status,
                host=args.host,
                recipient=args.recipient_file,
                encrypted=args.encrypted_dir,
                external=args.copy_to,
            )
    except Exception as exc:
        from ops.diagnostics import diagnostic

        diagnostic("backup_watch", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
