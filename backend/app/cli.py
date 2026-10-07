"""Comandos de linha: `python -m app.cli seed`."""

import asyncio
import logging
import sys

from app.db.seed import seed_lessons
from app.db.session import dispose_engine, get_sessionmaker


async def _seed() -> None:
    async with get_sessionmaker()() as session:
        total = await seed_lessons(session)
    await dispose_engine()
    print(f"✓ seed aplicado: {total} aulas")


def main_com_argumentos(argumentos: list[str]) -> None:
    """Separado de main() para o teste poder chamar sem mexer em sys.argv."""
    comando = argumentos[0] if argumentos else ""
    if comando == "seed":
        asyncio.run(_seed())
    else:
        print("uso: python -m app.cli seed", file=sys.stderr)
        raise SystemExit(2)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    main_com_argumentos(sys.argv[1:])


if __name__ == "__main__":
    main()
