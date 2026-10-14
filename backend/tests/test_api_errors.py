"""Contrato de erro sem banco: falhas injetadas apenas numa app local de teste."""

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from app.main import create_app


@pytest.mark.parametrize(
    ("status", "code"), [(401, "session_invalid"), (409, "conflict"), (503, "service_unavailable")]
)
async def test_common_errors_keep_detail_headers_and_request_id(status: int, code: str) -> None:
    app = create_app()

    @app.get("/error-fixture")
    async def fail() -> None:
        raise HTTPException(
            status,
            detail={"code": "practice_content_changed", "session_id": 7},
            headers={"WWW-Authenticate": "Bearer", "Retry-After": "3"},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/error-fixture", headers={"X-Request-ID": "safe-id"})
    assert result.status_code == status
    assert result.json() == {
        "code": code,
        "request_id": "safe-id",
        "detail": {"code": "practice_content_changed", "session_id": 7},
    }
    assert result.headers["x-error-code"] == code
    assert result.headers["www-authenticate"] == "Bearer"
    assert result.headers["retry-after"] == "3"
    assert result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "failure",
    [
        OperationalError("SQL segredo", {"password": "privada"}, Exception("privada")),
        InterfaceError("SQL segredo", {}, Exception("privada")),
        PoolTimeout("privada"),
        ConnectionRefusedError("privada"),
        TimeoutError("privada"),
    ],
)
async def test_dependency_failures_are_503_and_never_leak(failure: Exception) -> None:
    app = create_app()

    @app.get("/error-fixture")
    async def fail() -> None:
        raise failure

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/error-fixture", headers={"X-Request-ID": "invalid private id"})
    assert result.status_code == 503
    assert result.json()["code"] == "service_unavailable"
    assert result.json()["request_id"] == result.headers["x-request-id"]
    assert result.json()["request_id"] != "invalid private id"
    assert "privada" not in result.text
    assert "SQL" not in result.text


async def test_default_404_stays_compatible() -> None:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        result = await c.get("/does-not-exist")
    assert result.status_code == 404
    assert result.json() == {"detail": "Not Found"}


@pytest.mark.parametrize(
    ("sqlstate", "expected"),
    [("40P01", 503), ("40001", 503), ("55P03", 503), ("23505", 409), ("42501", 500)],
)
async def test_database_failures_do_not_expose_sql(sqlstate, expected):
    class DriverError(Exception):
        pass

    original = DriverError("private password")
    original.sqlstate = sqlstate
    app = create_app()

    @app.get("/error-fixture")
    async def fail():
        raise DBAPIError("private SQL", {"password": "private"}, original)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/error-fixture")
    assert result.status_code == expected
    assert "private" not in result.text and "SQL" not in result.text
