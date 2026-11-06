"""Diagnóstico de fronteira sem mensagem, SQL, caminho ou traceback privado."""

import json
import subprocess
import sys


def diagnostic(operation: str, error: BaseException) -> None:
    # Não usar type(error).__name__: até o nome de uma classe pode ser conteúdo externo.
    category = (
        "timeout"
        if isinstance(error, (TimeoutError, subprocess.TimeoutExpired))
        else "permission"
        if isinstance(error, PermissionError)
        else "io"
        if isinstance(error, OSError)
        else "subprocess"
        if isinstance(error, subprocess.SubprocessError)
        else "invalid_data"
        if isinstance(error, (ValueError, KeyError, TypeError))
        else "internal"
    )
    print(
        json.dumps({"event": "operation_failed", "operation": operation, "category": category}),
        file=sys.stderr,
    )
