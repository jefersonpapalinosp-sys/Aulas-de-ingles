"""Engine e sessão assíncronas do SQLAlchemy."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.role_safety import connect_args, guard_role_engine
from app.db.test_safety import guard_test_engine, validate_test_target
from app.performance import install_performance_listeners

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Engine único do processo, criado na primeira chamada."""
    global _engine
    if _engine is None:
        settings = get_settings()
        if settings.app_env == "test":
            validate_test_target(settings.database_url, settings.app_env)
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            connect_args=connect_args(
                settings.database_purpose,
                {
                    "statement_timeout": str(settings.database_statement_timeout_ms),
                    "lock_timeout": str(settings.database_lock_timeout_ms),
                },
            ),
        )
        install_performance_listeners(_engine)
        if settings.app_env == "test":
            guard_test_engine(_engine, settings.database_url, settings.app_env)
        if settings.database_purpose:
            guard_role_engine(_engine, settings.database_purpose)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependência do FastAPI: uma sessão por request."""
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    """Fecha o pool no shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
