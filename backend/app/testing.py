"""Preparação segura da base exclusiva de testes, sem fallback para dev/prod."""

import asyncio
import os
import subprocess
import sys

from sqlalchemy import text

from app.db.test_safety import UnsafeTestDatabase, configure_test_environment


async def check_database() -> None:
    from app.db.session import dispose_engine, get_engine

    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await dispose_engine()


def main() -> None:
    try:
        configure_test_environment(os.environ)
        asyncio.run(check_database())
    except UnsafeTestDatabase as error:
        print(f"Teste bloqueado: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    except Exception:
        print("Base de testes indisponível. Execute make test-db-up.", file=sys.stderr)
        raise SystemExit(2) from None

    command = sys.argv[1] if len(sys.argv) > 1 else "check"
    if command == "check":
        print("✓ base descartável e papel limitado confirmados")
    elif command == "prepare":
        # A guarda também é aplicada às conexões dos subprocessos em APP_ENV=test.
        for args in (["alembic", "upgrade", "head"], ["app.cli", "seed"]):
            subprocess.run([sys.executable, "-m", *args], check=True)
    else:
        print("uso: python -m app.testing check | prepare", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
