"""Gera o contrato OpenAPI sem precisar do servidor no ar."""

import json
from pathlib import Path
from typing import Any

BASELINE = Path(__file__).resolve().parents[1] / "openapi.json"


def build() -> dict[str, Any]:
    from app.main import create_app

    spec: dict[str, Any] = create_app().openapi()
    return spec


def dumps(spec: dict[str, Any] | None = None) -> str:
    return json.dumps(spec or build(), indent=4, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    BASELINE.write_text(dumps(), encoding="utf-8")
    print(f"✓ {BASELINE} atualizado")
