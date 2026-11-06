"""Cliente do comando SSH fixo: SHA aprovado ou rollback, sem shell remoto livre."""

import argparse
import os
import re
from collections.abc import Sequence

from ops import public_probe
from ops.deploy_release import run
from ops.diagnostics import diagnostic
from ops.recovery_archive import require


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sha", nargs="?")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    args = parser.parse_args(argv)
    try:
        host = os.environ.get("AULAS_PUBLIC_SSH_HOST", "")
        require(
            re.fullmatch(r"(?!root@)[A-Za-z0-9_][A-Za-z0-9._-]*@[A-Za-z0-9][A-Za-z0-9.-]*", host),
            "Configure o host e usuário operacional; root não é aceito.",
        )
        require(args.rollback != bool(args.sha), "Informe SHA ou --rollback.")
        if args.rollback:
            command = "rollback"
        else:
            require(re.fullmatch(r"[a-fA-F0-9]{7,40}", args.sha), "SHA inválido.")
            full = (
                run(["git", "rev-parse", "--verify", f"{args.sha}^{{commit}}"], timeout=15)
                .decode()
                .strip()
            )
            require(re.fullmatch(r"[a-f0-9]{40}", full), "Commit inválido.")
            run(["git", "merge-base", "--is-ancestor", full, "origin/main"], timeout=15)
            command = f"deploy {full}"
        url = os.environ.get("AULAS_PUBLIC_URL", "")
        if not args.skip_smoke:
            public_probe.public_url(url)
        if args.dry_run:
            print(f"Prévia: SSH restrito executará {command}; nenhum contato remoto.")
            return 0
        result = run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ConnectTimeout=10",
                host,
                command,
            ],
            timeout=1830,
        )
        print(result.decode(), end="")
        if not args.skip_smoke:
            return public_probe.main(["--base-url", url])
        return 0
    except Exception as exc:
        diagnostic("deploy_client", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
