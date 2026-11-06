"""Comando fixo instalado fora do código publicado; nenhuma shell vinda do SSH."""

import json
import os
import re
import signal
import sys
from pathlib import Path

from ops.deploy_release import Releases, lock
from ops.diagnostics import diagnostic
from ops.recovery_archive import require

CONFIG = Path("/etc/aulas-deploy.json")


def parse(command: str) -> tuple[str, str | None]:
    if command == "rollback":
        return "rollback", None
    match = re.fullmatch(r"deploy ([a-f0-9]{40})", command)
    require(match is not None, "Comando SSH não permitido.")
    assert match is not None
    return "deploy", match[1]


def main() -> int:
    try:
        require(os.geteuid() != 0, "Deploy deve usar o usuário operacional, não root.")
        require(not CONFIG.is_symlink() and CONFIG.is_file(), "Configuração instalada ausente.")
        require(
            CONFIG.stat().st_mode & 0o022 == 0 and CONFIG.stat().st_uid == 0,
            "Configuração precisa pertencer a root e impedir escrita do grupo.",
        )
        local_adopt = sys.argv[1:] == ["adopt"] and "SSH_ORIGINAL_COMMAND" not in os.environ
        action, sha = (
            ("adopt", None) if local_adopt else parse(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
        )
        release = Releases(json.loads(CONFIG.read_text()))

        def expired(signum: int, frame: object) -> None:
            raise TimeoutError("Tempo total de deploy excedido.")

        signal.signal(signal.SIGALRM, expired)
        signal.signal(signal.SIGTERM, expired)
        signal.signal(signal.SIGHUP, expired)
        signal.alarm(1800)
        with lock(release.state / "deploy.lock"):
            if action == "deploy":
                assert sha is not None
                release.deploy(sha)
            elif action == "rollback":
                release.rollback()
            else:
                release.adopt()
        return 0
    except Exception as exc:
        diagnostic("deploy_server", exc)
        return 1
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
