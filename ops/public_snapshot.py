"""Mantém o snapshot PostgreSQL vivo enquanto pg_dump importa a mesma visão."""

import json
import queue
import re
import shlex
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from ops import recovery
from ops.recovery_archive import RecoveryError, require

if TYPE_CHECKING:
    from ops.public_backup import Snapshot


@contextmanager
def exported_snapshot(host: str) -> Iterator[tuple["Snapshot", str]]:
    from ops import public_backup as public

    remote = f"docker exec -i {public.container('db')} sh -c " + shlex.quote(
        f'psql -U {public.BACKUP_ROLE} -d "$POSTGRES_DB" -XqAt -v ON_ERROR_STOP=1'
    )
    process = subprocess.Popen(
        public.transport(host, remote),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert process.stdin is not None and process.stdout is not None
        sql = (
            "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
            "SET LOCAL idle_in_transaction_session_timeout='20min';\n"
            "SET LOCAL statement_timeout='60s';\n"
            "SELECT json_build_object('token',pg_export_snapshot(),'snapshot',("
            + recovery.SNAPSHOT_SQL.strip()
            + "));\n"
        )
        process.stdin.write(sql.encode())
        process.stdin.flush()
        result: queue.Queue[bytes] = queue.Queue(maxsize=1)
        stdout = process.stdout

        def read() -> None:
            try:
                result.put(stdout.readline(32 * 1024 * 1024 + 1))
            except OSError:
                result.put(b"")

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            raw = result.get(timeout=70)
        except queue.Empty as exc:
            raise RecoveryError("Snapshot exportado excedeu o tempo limite.") from exc
        require(
            raw.endswith(b"\n") and len(raw) <= 32 * 1024 * 1024,
            "Snapshot exportado incompleto ou excessivo.",
        )
        value = json.loads(raw)
        token = value.get("token")
        require(
            isinstance(token, str) and re.fullmatch(r"[0-9A-Fa-f]+-[0-9A-Fa-f]+-\d+", token),
            "Identificador de snapshot inválido.",
        )
        assert isinstance(token, str)
        snapshot = public.checked_snapshot(value.get("snapshot"))
        yield snapshot, token
        require(process.poll() is None, "Sessão exportadora terminou antes da captura.")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RecoveryError("Sessão de snapshot falhou; backup não confirmado.") from exc
    finally:
        # EOF encerra a sessão e desfaz a transação; não deixa processo/thread preso.
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
