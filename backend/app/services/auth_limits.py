"""Proteção distribuída de login/registro; Argon2 sai do event loop com teto explícito."""

import asyncio
import hashlib
import hmac
import time
from collections.abc import Callable
from weakref import WeakKeyDictionary

import anyio
from fastapi import HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import AuthRateBucket

_limiters: WeakKeyDictionary[asyncio.AbstractEventLoop, anyio.CapacityLimiter] = WeakKeyDictionary()


async def password_work[T](fn: Callable[..., T], *args: str) -> T:
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = anyio.CapacityLimiter(get_settings().auth_hash_concurrency)
    # Cancelamento não libera a vaga enquanto o hash ainda consome memória.
    with anyio.move_on_after(10) as deadline:
        result = await anyio.to_thread.run_sync(
            fn, *args, limiter=_limiters[loop], abandon_on_cancel=False
        )
    if deadline.cancel_called:
        raise HTTPException(503, "Autenticação ocupada. Aguarde e tente novamente.")
    return result


async def rate_limit(session: AsyncSession, request: Request, email: str) -> None:
    settings = get_settings()
    now = int(time.time())
    start = now - now % settings.auth_window_seconds
    # X-Forwarded-For não é confiável por padrão. request.client é a origem
    # resolvida pelo servidor/proxy explicitamente confiável no deploy.
    origin = request.client.host if request.client else "unknown"
    entries = [
        ("identity:" + email, settings.auth_identity_limit),
        ("origin:" + origin, settings.auth_origin_limit),
    ]
    hashed = sorted(
        (hmac.new(settings.auth_bucket_key, value.encode(), hashlib.sha256).hexdigest(), limit)
        for value, limit in entries
    )
    blocked = False
    await session.execute(delete(AuthRateBucket).where(AuthRateBucket.window_start < start - 86400))
    for key, limit in hashed:
        statement = insert(AuthRateBucket).values(key=key, window_start=start, count=1)
        count = (
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[AuthRateBucket.key, AuthRateBucket.window_start],
                    set_={"count": AuthRateBucket.count + 1},
                ).returning(AuthRateBucket.count)
            )
        ).scalar_one()
        blocked |= count > limit
    await session.commit()
    if blocked:
        raise HTTPException(
            429,
            "Muitas tentativas. Aguarde antes de tentar novamente.",
            headers={"Retry-After": str(start + settings.auth_window_seconds - now)},
        )
