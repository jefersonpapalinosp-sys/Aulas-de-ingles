"""Health check contra o Postgres real do compose — sem mock de banco."""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from app.api import health
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
    assert body["schema"] == "compatible"
    assert body["schema_current"] == body["schema_required"]
    assert body["schema_current"] == ["f40c2d9a1b73"]
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
    assert body["schema"] == "unknown"


@pytest.mark.asyncio
async def test_health_schema_antigo_mantem_live_positivo_e_readiness_negativa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Scalars:
        def all(self) -> list[str]:
            return ["revision-antiga"]

    class Resultado:
        def scalar_one(self) -> str:
            return "PostgreSQL 16.15 synthetic"

        def scalars(self) -> Scalars:
            return Scalars()

    class SessaoSchemaAntigo:
        async def execute(self, *args: Any, **kwargs: Any) -> Resultado:
            return Resultado()

    monkeypatch.setattr(health, "required_schema_heads", lambda: ("revision-nova",))
    app = create_app()

    async def sessao_schema_antigo() -> Any:
        yield SessaoSchemaAntigo()

    app.dependency_overrides[get_session] = sessao_schema_antigo
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        live = await c.get("/api/live")
        ready = await c.get("/api/health")

    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.headers["x-error-code"] == "schema_incompatible"
    assert ready.json() == {
        "status": "degraded",
        "db": "up",
        "version": "PostgreSQL 16.15",
        "schema": "incompatible",
        "schema_current": ["revision-antiga"],
        "schema_required": ["revision-nova"],
        "env": "test",
        "code": "schema_incompatible",
    }


@pytest.mark.asyncio
async def test_health_tabela_de_versao_ausente_e_incompatibilidade_sem_vazar_erro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Resultado:
        def scalar_one(self) -> str:
            return "PostgreSQL 16.15 synthetic"

    class SessaoSemCatalogo:
        calls = 0

        async def execute(self, *args: Any, **kwargs: Any) -> Resultado:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("segredo SQL que não pode ir para a resposta")
            return Resultado()

    monkeypatch.setattr(health, "required_schema_heads", lambda: ("revision-nova",))
    app = create_app()

    async def sessao_sem_catalogo() -> Any:
        yield SessaoSemCatalogo()

    app.dependency_overrides[get_session] = sessao_sem_catalogo
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        result = await c.get("/api/health")

    assert result.status_code == 503
    assert result.json()["schema"] == "incompatible"
    assert result.json()["schema_current"] == []
    assert "segredo" not in result.text
