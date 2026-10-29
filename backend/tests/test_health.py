"""Health check contra o Postgres real do compose — sem mock de banco."""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from app.api import health
from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app

TOKEN = "readiness-test-token-with-at-least-32-bytes"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def operational_token(monkeypatch):
    monkeypatch.setattr(get_settings(), "operations_token", TOKEN)


@pytest.mark.asyncio
async def test_live_nao_toca_dependencia(client: AsyncClient) -> None:
    r = await client.get("/api/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_com_banco_de_pe(client: AsyncClient) -> None:
    r = await client.get("/api/operations/readiness", headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "up"
    assert body["version"].startswith("PostgreSQL")
    assert body["schema"] == "compatible"
    assert body["schema_current"] == body["schema_required"]
    assert body["schema_current"] == ["c92f4a8d710e"]
    assert body["env"] == "test"
    assert r.headers["cache-control"] == "private, no-store"


async def test_health_publico_preserva_readiness_sem_detalhes(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "up", "schema": "compatible", "code": None}
    assert response.headers["cache-control"] == "private, no-store"
    # Mesmo com token, o endereço público não ganha detalhes.
    authenticated = await client.get("/api/health", headers=AUTH)
    assert authenticated.json() == response.json()


@pytest.mark.parametrize("configured", [True, False])
async def test_readiness_privada_autoriza_antes_de_consultar_banco(monkeypatch, configured):
    monkeypatch.setattr(get_settings(), "operations_token", TOKEN if configured else None)

    class ForbiddenSession:
        async def execute(self, *args, **kwargs):
            pytest.fail("Diagnóstico sem autorização não pode consultar o banco.")

    app = create_app()

    async def forbidden():
        yield ForbiddenSession()

    app.dependency_overrides[get_session] = forbidden
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for headers in ({}, {"Authorization": "Bearer wrong-private-token"}):
            response = await client.get("/api/operations/readiness", headers=headers)
            assert response.status_code == (401 if configured else 404)
            assert "wrong-private-token" not in response.text
            assert "schema_required" not in response.text


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
        r = await c.get("/api/operations/readiness", headers=AUTH)
        public = await c.get("/api/health")

    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "down"
    assert body["version"] is None
    assert body["schema"] == "unknown"
    assert public.status_code == 503
    assert public.json() == {
        "status": "degraded",
        "db": "down",
        "schema": "unknown",
        "code": "service_unavailable",
    }


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
        ready = await c.get("/api/operations/readiness", headers=AUTH)
        public = await c.get("/api/health")

    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.headers["x-error-code"] == "schema_incompatible"
    assert public.status_code == 503
    assert public.json() == {
        "status": "degraded",
        "db": "up",
        "schema": "incompatible",
        "code": "schema_incompatible",
    }
    assert "revision-" not in public.text and "PostgreSQL" not in public.text
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
        result = await c.get("/api/operations/readiness", headers=AUTH)

    assert result.status_code == 503
    assert result.json()["schema"] == "incompatible"
    assert result.json()["schema_current"] == []
    assert "segredo" not in result.text
