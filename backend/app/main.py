"""Entrypoint da API."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    assist,
    auth,
    courses,
    dashboard,
    health,
    lessons,
    me,
    media,
    practice,
    progress,
    review,
    speaking,
    writing,
)
from app.core.config import get_settings
from app.core.logging import configurar, middleware_request_id
from app.db.session import dispose_engine


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
    )
    app.middleware("http")(middleware_request_id)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(health.router, prefix="/api")
    app.include_router(courses.router, prefix="/api")
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
    return app


app = create_app()
