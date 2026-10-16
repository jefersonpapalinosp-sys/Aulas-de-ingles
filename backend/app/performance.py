"""Opt-in request measurements without collecting SQL text or response content."""

import logging
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings

SQL_HEADER = "X-Perf-SQL-Queries"
BYTES_HEADER = "X-Perf-Response-Bytes"
DURATION_HEADER = "X-Perf-Duration-Ms"
POOL_HEADER = "X-Perf-Pool-Checkouts"


@dataclass(slots=True)
class RequestPerformance:
    started_at: float
    sql_queries: int = 0
    pool_checkouts: int = 0


_current_sample: ContextVar[RequestPerformance | None] = ContextVar(
    "request_performance", default=None
)


def install_performance_listeners(engine: AsyncEngine) -> None:
    """Attach counters to one engine without retaining SQL or parameters."""

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def count_query(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        sample = _current_sample.get()
        if sample is not None:
            sample.sql_queries += 1

    @event.listens_for(engine.sync_engine.pool, "checkout")
    def count_checkout(connection: Any, record: Any, proxy: Any) -> None:
        sample = _current_sample.get()
        if sample is not None:
            sample.pool_checkouts += 1


def _response_size(response: Response) -> int | None:
    value = response.headers.get("content-length")
    if value is None or not value.isdecimal():
        return None
    return int(value)


def _record(
    request: Request,
    status_code: int,
    sample: RequestPerformance,
    response_bytes: int | None,
) -> float:
    duration_ms = round((time.perf_counter() - sample.started_at) * 1000, 2)
    logging.getLogger("app.performance").info(
        "request performance",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": status_code,
            "duration_ms": duration_ms,
            "sql_queries": sample.sql_queries,
            "response_bytes": response_bytes,
            "pool_checkouts": sample.pool_checkouts,
        },
    )
    return duration_ms


async def middleware_performance(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Measure local/test requests and publish aggregate diagnostic headers."""
    settings = get_settings()
    if (
        not settings.performance_probe_enabled
        or settings.app_env == "prod"
        or settings.deployment_profile == "public"
    ):
        return await call_next(request)

    sample = RequestPerformance(started_at=time.perf_counter())
    token: Token[RequestPerformance | None] = _current_sample.set(sample)
    try:
        response = await call_next(request)
    except Exception:
        _record(request, 500, sample, None)
        raise
    finally:
        _current_sample.reset(token)

    response_bytes = _response_size(response)
    duration_ms = _record(request, response.status_code, sample, response_bytes)
    response.headers[SQL_HEADER] = str(sample.sql_queries)
    response.headers[DURATION_HEADER] = f"{duration_ms:.2f}"
    response.headers[POOL_HEADER] = str(sample.pool_checkouts)
    if response_bytes is not None:
        response.headers[BYTES_HEADER] = str(response_bytes)
    response.headers["Server-Timing"] = f"app;dur={duration_ms:.2f}"
    return response
