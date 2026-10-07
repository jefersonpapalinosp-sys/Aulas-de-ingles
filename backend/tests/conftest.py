import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

# Nos testes o Postgres é o do compose, exposto no host.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://aulas:aulas_local@localhost:5433/aulas_ingles"
)
os.environ.setdefault("APP_ENV", "test")

from sqlalchemy import delete  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import dispose_engine, get_sessionmaker  # noqa: E402
from app.main import create_app  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def banco_por_teste() -> AsyncIterator[None]:
    """Isola cada teste.

    Duas coisas acontecem no teardown, nesta ordem:

    1. Apaga as contas criadas. O conteúdo das aulas é fixture permanente (vem
       do seed), mas usuário é dado de teste — deixá-lo para trás faz o
       segundo `pytest` falhar com 409. Apagar o usuário leva junto sessão,
       progresso e tentativas, por cascade.
    2. Descarta o engine. O pool é um singleton do processo e o pytest-asyncio
       abre um event loop por teste: sem isso, o teste seguinte pega conexões
       presas no loop anterior, já fechado.

    Por ser autouse, este fixture é montado antes dos outros e desmontado
    depois — o que garante que a limpeza roda com o loop ainda vivo.
    """
    yield

    async with get_sessionmaker()() as s:
        await s.execute(delete(User))
        await s.commit()
    await dispose_engine()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Sessão direta no Postgres do compose, para testar o seed e os modelos."""
    async with get_sessionmaker()() as s:
        yield s


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
