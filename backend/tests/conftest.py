import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

# Nos testes o Postgres é o do compose, exposto no host.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://aulas:aulas_local@localhost:5433/aulas_ingles"
)
os.environ.setdefault("APP_ENV", "test")

from app.core.config import get_settings  # noqa: E402
from app.db.session import dispose_engine  # noqa: E402
from app.main import create_app  # noqa: E402

get_settings.cache_clear()


@pytest.fixture
async def session() -> AsyncIterator[Any]:
    """Sessão direta no Postgres do compose, para testar o seed e os modelos."""
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as s:
        yield s
    await dispose_engine()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await dispose_engine()
