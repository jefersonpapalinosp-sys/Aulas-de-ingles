"""Executa o gate para cron: sucesso silencioso, falha com relatório sanitizado."""

import contextlib
import io
import sys
from datetime import UTC, datetime

from ops import observability_check


def main(argv: list[str] | None = None) -> int:
    output = io.StringIO()
    errors = io.StringIO()
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = observability_check.main(argv)
    except Exception as exc:
        from ops.diagnostics import diagnostic
        diagnostic("operations_alert", exc)
        # Não publicar exceção, URL, resposta de fornecedor ou variável de ambiente.
        print("ALERTA operacional: falha interna na execução do gate.", file=sys.stderr)
        return 2
    if status:
        timestamp = datetime.now(UTC).isoformat()
        print(f"ALERTA operacional em {timestamp} (saída {status}).", file=sys.stderr)
        # O gate emite somente checks agregados e mensagens fixas sanitizadas.
        for report in (output.getvalue(), errors.getvalue()):
            if report:
                print(report.rstrip(), file=sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
