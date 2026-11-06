"""Bloqueia CRITICAL e falha fechada quando o inventário Trivy não é válido."""

import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ops.recovery_archive import require


def critical_count(path: Path) -> int:
    require(path.is_file() and not path.is_symlink(), "Relatório ausente.")
    report = json.loads(path.read_text(encoding="utf-8"))
    require(
        isinstance(report, dict)
        and report.get("SchemaVersion") == 2
        and report.get("ArtifactType") == "container_image"
        and isinstance(report.get("Results"), list)
        and bool(report["Results"]),
        "Inventário incompleto.",
    )
    count = 0
    for result in report["Results"]:
        require(isinstance(result, dict) and result.get("Target"), "Resultado inválido.")
        findings = result.get("Vulnerabilities")
        if findings is None:
            findings = []
        require(isinstance(findings, list), "Vulnerabilidades inválidas.")
        for finding in findings:
            require(
                isinstance(finding, dict)
                and finding.get("Severity") in {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"},
                "Achado inválido.",
            )
            count += finding["Severity"] == "CRITICAL"
    return count


def main(argv: Sequence[str] | None = None) -> int:
    try:
        paths = list(argv if argv is not None else sys.argv[1:])
        require(len(paths) >= 2, "Exija os inventários da API e web.")
        count = sum(critical_count(Path(path)) for path in paths)
        print(f"Vulnerabilidades CRITICAL: {count}")
        return 1 if count else 0
    except Exception:
        print("Gate de segurança recusado: relatório ausente ou inválido.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
