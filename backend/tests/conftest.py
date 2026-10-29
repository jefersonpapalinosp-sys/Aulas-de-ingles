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

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import dispose_engine, get_sessionmaker  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.db_isolation import catalog_transaction, reset_transient_data  # noqa: E402

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
    """Limpa tabelas fora do seed antes/depois do cenário e descarta o pool.

    Preserva commits reais e conexões independentes usados pela API/worker.
    Conteúdo temporário usa catalog_lab com rollback externo. Testes puros
    não dependem desta fixture e não abrem conexão. Toda limpeza confirma
    novamente a identidade descartável do banco e usa TRUNCATE RESTRICT.
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
            await reset_transient_data(s)
            await s.commit()
    except Exception:
        await dispose_engine()
        raise
    try:
        yield
    finally:
        try:
            async with get_sessionmaker()() as s:
                await reset_transient_data(s)
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


@pytest.fixture
async def catalog_lab(
    banco_por_teste: None,
) -> AsyncIterator[tuple[AsyncSession, AsyncClient]]:
    """Conteúdo curricular temporário visível à API, sem sobreviver ao teste."""
    async with catalog_transaction() as context:
        yield context
