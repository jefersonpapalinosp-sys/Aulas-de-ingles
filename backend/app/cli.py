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


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando == "seed":
        asyncio.run(_seed())
    else:
        print("uso: python -m app.cli seed", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
