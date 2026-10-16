"""Entrypoint da API."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, StreamingResponse

from app.api import (
    activity,
    assist,
    auth,
    course_reviews,
    courses,
    dashboard,
    health,
    history,
    lessons,
    me,
    media,
    practice,
    progress,
    review,
    speaking,
    writing,
)
from app.api.errors import ERROR_RESPONSES, database_error, http_error, unavailable
from app.core.config import get_settings
from app.core.logging import configurar, middleware_request_id
from app.db.session import dispose_engine
from app.performance import middleware_performance
from app.services.offline_policy import (
    if_none_match_matches,
    public_content_etag,
    public_text_path,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.getLogger(__name__).info(
        "API no ar", extra={"env": settings.app_env, "version": app.version}
    )
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configurar(settings.log_level)
    app = FastAPI(
        title="Aulas de Inglês — API",
        version="0.1.0",
        lifespan=lifespan,
        responses=ERROR_RESPONSES,
    )
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(DBAPIError, database_error)
    for error in (OperationalError, InterfaceError, PoolTimeout, ConnectionError, TimeoutError):
        app.add_exception_handler(error, unavailable)
    app.middleware("http")(middleware_performance)
    app.middleware("http")(middleware_request_id)

    @app.middleware("http")
    async def private_transport(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if (
            settings.deployment_profile == "public"
            and request.url.scheme != "https"
            and request.url.path != "/api/live"
        ):
            return JSONResponse(
                {"detail": "HTTPS obrigatório."},
                status_code=426,
                headers={"Cache-Control": "no-store"},
            )
        result = await call_next(request)
        if request.url.path.startswith("/api/"):
            public_text = (
                request.method == "GET"
                and result.status_code == 200
                and result.headers.get("content-type", "").startswith("application/json")
                and public_text_path(request.url.path)
            )
            if public_text:
                result.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
                result.headers["X-Aulas-Offline"] = "public-text-v1"
                streaming = cast(StreamingResponse, result)
                parts: list[bytes] = []
                async for chunk in streaming.body_iterator:
                    parts.append(chunk.encode() if isinstance(chunk, str) else bytes(chunk))
                body = b"".join(parts)
                etag = public_content_etag(body)
                headers = dict(result.headers)
                headers["ETag"] = etag
                headers.pop("content-length", None)
                if if_none_match_matches(request.headers.get("if-none-match"), etag):
                    headers.pop("content-type", None)
                    result = Response(status_code=304, headers=headers)
                else:
                    result = Response(
                        content=body,
                        status_code=result.status_code,
                        headers=headers,
                        background=result.background,
                    )
            else:
                result.headers["Cache-Control"] = "private, no-store"
            result.headers["Pragma"] = "no-cache"
            result.headers["X-Content-Type-Options"] = "nosniff"
            if settings.deployment_profile == "public":
                result.headers["Strict-Transport-Security"] = "max-age=31536000"
        return result

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=[
                "X-Request-ID",
                "X-Error-Code",
                "X-Perf-SQL-Queries",
                "X-Perf-Response-Bytes",
                "X-Perf-Duration-Ms",
                "X-Perf-Pool-Checkouts",
                "Server-Timing",
                "ETag",
                "X-Aulas-Offline",
            ],
        )
    app.include_router(health.router, prefix="/api")
    app.include_router(history.router, prefix="/api")
    app.include_router(courses.router, prefix="/api")
    app.include_router(course_reviews.router, prefix="/api")
    app.include_router(lessons.router, prefix="/api")
    app.include_router(media.router, prefix="/api")
    app.include_router(practice.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(progress.router, prefix="/api")
    app.include_router(review.router, prefix="/api")
    app.include_router(writing.router, prefix="/api")
    app.include_router(speaking.router, prefix="/api")
    app.include_router(me.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(assist.router, prefix="/api")
    app.include_router(activity.router, prefix="/api")
    return app


app = create_app()
