"""Health check contra o Postgres real do compose — sem mock de banco."""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_session
from app.main import create_app


@pytest.mark.asyncio
async def test_live_nao_toca_dependencia(client: AsyncClient) -> None:
    r = await client.get("/api/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_com_banco_de_pe(client: AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "up"
    assert body["version"].startswith("PostgreSQL")
    assert body["env"] == "test"


@pytest.mark.asyncio
async def test_health_com_banco_fora_devolve_503() -> None:
    """Banco fora do ar precisa virar 503, não 200 com mentira dentro.

    A sessão do SQLAlchemy é preguiçosa: ela abre sem erro e só estoura no
    primeiro `execute`. Por isso a falha é injetada no execute, e não na
    criação da sessão — é assim que o Postgres fora do ar se manifesta.
    """

    class SessaoQueFalhaNoExecute:
        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            raise OperationalError("select version()", {}, Exception("conexão recusada"))

    app = create_app()

    async def sessao_quebrada() -> Any:
        yield SessaoQueFalhaNoExecute()

    app.dependency_overrides[get_session] = sessao_quebrada

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/health")

    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "down"
    assert body["version"] is None
