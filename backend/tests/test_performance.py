"""Sprint 41: observable, privacy-safe budgets for representative public reads."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.main import create_app
from app.performance import BYTES_HEADER, DURATION_HEADER, POOL_HEADER, SQL_HEADER


async def _register(client: AsyncClient, suffix: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"perf-{suffix}@example.com",
            "password": "senha-bem-grande",
            "display_name": "Performance",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_performance_probe_is_disabled_by_default(client: AsyncClient) -> None:
    response = await client.get("/api/lessons")

    assert response.status_code == 200
    assert SQL_HEADER not in response.headers
    assert BYTES_HEADER not in response.headers
    assert DURATION_HEADER not in response.headers
    assert POOL_HEADER not in response.headers
    assert "Server-Timing" not in response.headers


@pytest.mark.asyncio
async def test_performance_probe_measures_public_list_without_reading_content(
    banco_por_teste: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "performance_probe_enabled", True)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        response = await c.get("/api/lessons")

    assert response.status_code == 200
    assert int(response.headers[SQL_HEADER]) == 1
    assert int(response.headers[BYTES_HEADER]) == len(response.content)
    assert float(response.headers[DURATION_HEADER]) >= 0
    assert int(response.headers[POOL_HEADER]) <= 1
    assert response.headers["Server-Timing"].startswith("app;dur=")


@pytest.mark.asyncio
async def test_lesson_detail_baseline_has_an_explicit_query_budget(
    banco_por_teste: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "performance_probe_enabled", True)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        response = await c.get("/api/courses/voa-level-1/lessons/31")

    assert response.status_code == 200
    # Baseline medida antes desta projeção: 18. O detalhe não pode voltar a
    # carregar checkpoint/perguntas da unidade nem gabaritos dos exercícios.
    assert int(response.headers[SQL_HEADER]) <= 15
    assert int(response.headers[BYTES_HEADER]) == len(response.content)
    assert int(response.headers[POOL_HEADER]) <= 1


@pytest.mark.asyncio
async def test_today_baseline_does_not_query_each_checkpoint_or_full_lesson(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _register(client, "today")
    monkeypatch.setattr(get_settings(), "performance_probe_enabled", True)

    response = await client.get("/api/me/today", headers=headers)

    assert response.status_code == 200
    assert response.json()["recommendation"]["kind"] == "start_lesson"
    assert int(response.headers[SQL_HEADER]) <= 8
    assert int(response.headers[BYTES_HEADER]) == len(response.content)
    assert int(response.headers[POOL_HEADER]) <= 1


@pytest.mark.parametrize(
    "settings",
    [
        Settings(app_env="prod", jwt_secret="p" * 32, performance_probe_enabled=True),
        Settings(
            deployment_profile="public",
            cookie_secure=True,
            public_origin="https://study.example",
            performance_probe_enabled=True,
        ),
    ],
)
def test_performance_probe_is_rejected_outside_local_non_production(settings: Settings) -> None:
    with pytest.raises(RuntimeError, match="local/teste"):
        settings.validar()
