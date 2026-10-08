"""Comandos operacionais da aplicação."""

import asyncio
import json
import logging
import sys
from pathlib import Path

from app.core.config import get_settings
from app.db.seed import seed_lessons
from app.db.session import dispose_engine, get_sessionmaker
from app.services.assist_gate import (
    Modality,
    collect_gate_metrics,
    evaluate_gate,
    load_provider_review,
)


async def _seed() -> None:
    async with get_sessionmaker()() as session:
        total = await seed_lessons(session)
    await dispose_engine()
    print(f"✓ seed aplicado: {total} aulas")


async def _assist_gate(modality: Modality, review_path: Path) -> bool:
    review = load_provider_review(review_path)
    async with get_sessionmaker()() as session:
        metrics = await collect_gate_metrics(session, modality)
    await dispose_engine()
    report = evaluate_gate(modality, metrics, review, get_settings())
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return report.approved


def main_com_argumentos(argumentos: list[str]) -> None:
    """Separado de main() para o teste poder chamar sem mexer em sys.argv."""
    comando = argumentos[0] if argumentos else ""
    if comando == "seed":
        asyncio.run(_seed())
    elif comando == "assist-gate":
        try:
            modality_index = argumentos.index("--modality") + 1
            review_index = argumentos.index("--review-file") + 1
            modality = argumentos[modality_index]
            review_path = Path(argumentos[review_index])
        except (ValueError, IndexError):
            print(
                "uso: python -m app.cli assist-gate --modality "
                "transcription|writing --review-file caminho.json",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        if modality not in {"transcription", "writing"}:
            print("modalidade inválida: use transcription ou writing", file=sys.stderr)
            raise SystemExit(2)
        try:
            approved = asyncio.run(_assist_gate(modality, review_path))  # type: ignore[arg-type]
        except (OSError, ValueError) as error:
            print(f"manifesto inválido: {error}", file=sys.stderr)
            raise SystemExit(2) from None
        if not approved:
            raise SystemExit(1)
    else:
        print("uso: python -m app.cli seed | assist-gate", file=sys.stderr)
        raise SystemExit(2)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    main_com_argumentos(sys.argv[1:])


if __name__ == "__main__":
    main()
