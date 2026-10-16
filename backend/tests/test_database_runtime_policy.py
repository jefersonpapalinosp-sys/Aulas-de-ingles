"""Orçamento de conexões e timeouts efetivamente aplicados pelo runtime."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_engine


async def test_runtime_applies_pool_budget_and_database_timeouts(
    session: AsyncSession,
) -> None:
    settings = get_settings()
    statement, lock, maximum = (
        await session.execute(
            text(
                "SELECT current_setting('statement_timeout'),"
                "current_setting('lock_timeout'),"
                "current_setting('max_connections')::integer"
            )
        )
    ).one()
    pool = get_engine().pool

    assert statement == "30s"
    assert lock == "5s"
    assert pool.size() == settings.database_pool_size
    assert pool.timeout() == settings.database_pool_timeout_seconds
    assert settings.database_connection_budget == 20
    assert settings.database_connection_budget <= maximum - 10
