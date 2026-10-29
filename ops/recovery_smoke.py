"""Ensaio real exclusivamente sintético; requer laboratório preparado e destino vazio."""

import json
import os
import sys

from ops.recovery import (
    CONFIRM_TARGET,
    LAB,
    RESTORE,
    SNAPSHOT_SQL,
    backup,
    check_target,
    query,
    restore,
)
from ops.recovery_archive import RecoveryError, require, verify_bundle


def main() -> None:
    os.umask(0o077)
    check_target(LAB)
    check_target(RESTORE)
    snapshot = query(LAB, SNAPSHOT_SQL)
    require(
        snapshot["counts"]["users"] == 1 and snapshot["counts"]["speaking"] == 1,
        "Ensaio exige exatamente a fixture sintética, não dados reais.",
    )
    first, second = backup("lab"), backup("lab")
    require(first != second, "Pacotes colidiram.")
    for bundle in (first, second):
        manifest = verify_bundle(bundle)
        source, audio = manifest["source"], manifest["audio_files"]
        if not isinstance(source, dict) or not isinstance(audio, dict):
            raise RecoveryError("Origem/inventário do manifesto inválidos.")
        require(
            source["kind"] == "lab" and manifest["snapshot"] == snapshot,
            "Origem/snapshot não são os esperados.",
        )
        require(len(audio) == 1, "Áudio sintético ausente.")
    receipt = restore(first, CONFIRM_TARGET)
    try:
        restore(second, CONFIRM_TARGET)
    except RecoveryError as exc:
        require("PostgreSQL não está vazio" in str(exc), "Recusa diferente da esperada.")
    else:
        raise RecoveryError("Destino não vazio deveria ser recusado.")
    require(query(LAB, SNAPSHOT_SQL) == snapshot, "Origem alterada pelo ensaio.")
    require(query(RESTORE, SNAPSHOT_SQL) == snapshot, "Destino alterado pela recusa.")
    print(
        json.dumps(
            {
                "verified": True,
                "bundles": [str(first), str(second)],
                "receipt": str(receipt),
                "nonempty_restore_blocked": True,
                "snapshot_counts": snapshot["counts"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Ensaio falhou; preserve laboratório/pacotes para diagnóstico.", file=sys.stderr)
        raise SystemExit(1) from None
