import pytest
from httpx import AsyncClient

from app.api import operations
from app.core.config import get_settings

TOKEN = "operations-test-token-with-at-least-32-bytes"


@pytest.mark.asyncio
async def test_metrics_desabilitadas_parecem_recurso_ausente(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "operations_token", None)
    response = await client.get("/api/operations/metrics")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_metrics_exigem_bearer_sem_refletir_credencial(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "operations_token", TOKEN)
    response = await client.get(
        "/api/operations/metrics",
        headers={"Authorization": "Bearer credencial-privada-incorreta"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "credencial-privada" not in response.text


@pytest.mark.asyncio
async def test_metrics_agregadas_tem_cardinalidade_fixa_e_nenhum_conteudo(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "operations_token", TOKEN)
    monkeypatch.setattr(operations, "_disk_metrics", lambda path: (True, 10_000, 4_000))
    response = await client.get(
        "/api/operations/metrics",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert set(body) == {
        "sampled_at",
        "requests",
        "database",
        "transcription_queue",
        "account_deletions",
        "legacy_review",
        "media",
    }
    assert set(body["requests"]["latency_buckets_ms"]) == {
        "50",
        "100",
        "250",
        "500",
        "1000",
        "2500",
        "5000",
        "+Inf",
    }
    assert body["requests"]["scope"] == "process"
    assert body["database"]["size_bytes"] > 0
    assert len(body["database"]["largest_relations"]) <= 5
    assert all(
        set(item) == {"relation", "total_bytes"} for item in body["database"]["largest_relations"]
    )
    assert body["media"]["filesystem_capacity_bytes"] == 10_000
    assert body["media"]["filesystem_free_bytes"] == 4_000
    assert body["legacy_review"]["unlinked_cards"] == 0
    assert body["legacy_review"]["mismatched_links"] == 0
    serialized = response.text.lower()
    for forbidden in ("email", "transcript_text", "storage_key", "authorization", TOKEN.lower()):
        assert forbidden not in serialized
