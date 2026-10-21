import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.test_safety import UnsafeTestDatabase, configure_test_environment

try:
    configure_test_environment(os.environ)
except UnsafeTestDatabase as error:
    raise pytest.UsageError(str(error)) from None

from sqlalchemy import delete  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import AccountDeletionJob, AuthRateBucket, CourseUnit, User  # noqa: E402
from app.db.session import dispose_engine, get_sessionmaker  # noqa: E402
from app.main import create_app  # noqa: E402

get_settings.cache_clear()

# Quando o CI exporta LEGACY_WRITES_UNTIL (por exemplo, uma data no passado), a
# suíte respeita esse valor em vez de empurrar a janela expand: é assim que o
# contrato pós-cutover de 13/11/2026 é exercitado antes do dia.
LEGACY_WINDOW_FROM_ENV = "LEGACY_WRITES_UNTIL" in os.environ


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "legacy_client: escreve sem revisão de propósito; só roda enquanto a janela "
        "expand de LEGACY_WRITES_UNTIL estiver aberta.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not LEGACY_WINDOW_FROM_ENV or datetime.now(UTC) < get_settings().legacy_writes_until:
        return
    expired = pytest.mark.skip(
        reason="janela expand de LEGACY_WRITES_UNTIL expirada: cliente legado fora do contrato"
    )
    for item in items:
        if "legacy_client" in item.keywords:
            item.add_marker(expired)


@pytest.fixture
async def banco_por_teste(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Limpa somente a base marcada como descartável nos testes de integração.

    Duas coisas acontecem no teardown, nesta ordem:

    1. Apaga as contas criadas. O conteúdo das aulas é fixture permanente (vem
       do seed), mas usuário é dado de teste — deixá-lo para trás faz o
       segundo `pytest` falhar com 409. Apagar o usuário leva junto sessão,
       progresso e tentativas, por cascade.
    2. Descarta o engine. O pool é um singleton do processo e o pytest-asyncio
       abre um event loop por teste: sem isso, o teste seguinte pega conexões
       presas no loop anterior, já fechado.

    client/session dependem desta fixture. Testes puros não abrem conexão e
    não executam DELETE. A guarda de conexão roda antes do teste e novamente
    ao obter qualquer nova conexão física (inclusive no teardown).
    """
    # Testes legados exercitam explicitamente a janela expand. Sua expiração
    # é coberta separadamente em test_concurrency e, no CI, por uma execução
    # com LEGACY_WRITES_UNTIL no passado (ver pytest_collection_modifyitems).
    if not LEGACY_WINDOW_FROM_ENV:
        monkeypatch.setattr(
            get_settings(), "legacy_writes_until", datetime.now(UTC) + timedelta(days=30)
        )
    try:
        async with get_sessionmaker()() as s:
            await s.connection()
    except Exception:
        await dispose_engine()
        raise
    try:
        yield
    finally:
        try:
            async with get_sessionmaker()() as s:
                await s.execute(delete(User))
                await s.execute(delete(AccountDeletionJob))
                await s.execute(delete(AuthRateBucket))
                await s.execute(delete(CourseUnit).where(CourseUnit.slug == "31-35"))
                await s.commit()
        finally:
            await dispose_engine()


@pytest.fixture
async def session(banco_por_teste: None) -> AsyncIterator[AsyncSession]:
    """Sessão direta no Postgres exclusivo dos testes."""
    async with get_sessionmaker()() as s:
        yield s


@pytest.fixture
async def client(banco_por_teste: None) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
