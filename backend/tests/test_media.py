"""Retomada de mídia autenticada e isolada por conta."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def conta(client: AsyncClient, sufixo: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"midia-{sufixo}@exemplo.com",
            "password": "senha-bem-grande",
            "display_name": sufixo,
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_posicao_de_midia_persiste_e_e_isolada(client: AsyncClient) -> None:
    media_id = (await client.get("/api/lessons/31")).json()["media"][0]["id"]
    assert (await client.get(f"/api/media/{media_id}/position")).status_code == 401

    ana = await conta(client, "ana")
    inicial = (await client.get(f"/api/media/{media_id}/position", headers=ana)).json()
    assert inicial == {"media_id": media_id, "position_seconds": 0.0, "updated_at": None}

    salvo = await client.put(
        f"/api/media/{media_id}/position",
        headers=ana,
        json={"position_seconds": 42.5},
    )
    assert salvo.status_code == 200
    assert salvo.json()["position_seconds"] == 42.5
    assert salvo.json()["updated_at"] is not None

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as outro:
        bruno = await conta(outro, "bruno")
        assert (await outro.get(f"/api/media/{media_id}/position", headers=bruno)).json()[
            "position_seconds"
        ] == 0

    assert (await client.delete(f"/api/media/{media_id}/position", headers=ana)).status_code == 204
    assert (await client.get(f"/api/media/{media_id}/position", headers=ana)).json()[
        "position_seconds"
    ] == 0


@pytest.mark.asyncio
async def test_posicao_valida_midia_e_duracao(client: AsyncClient) -> None:
    headers = await conta(client, "limites")
    media = (await client.get("/api/lessons/31")).json()["media"][0]

    negativo = await client.put(
        f"/api/media/{media['id']}/position",
        headers=headers,
        json={"position_seconds": -1},
    )
    alem = await client.put(
        f"/api/media/{media['id']}/position",
        headers=headers,
        json={"position_seconds": media["duration_seconds"] + 1},
    )
    ausente = await client.get("/api/media/999999/position", headers=headers)

    assert negativo.status_code == 422
    assert alem.status_code == 422
    assert ausente.status_code == 404


@pytest.mark.asyncio
async def test_midia_da_aula_14_level_2_respeita_duracao_oficial(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "level-2-14")
    lesson = (await client.get("/api/courses/voa-level-2/lessons/14")).json()
    media = lesson["media"][0]

    assert media["duration_seconds"] == 276
    assert media["source_url"].endswith("e2fe076d-3fa7-495a-83ea-9d4d4cba9fad_hq.mp3")
    saved = await client.put(
        f"/api/media/{media['id']}/position",
        headers=headers,
        json={"position_seconds": 275.5},
    )
    outside = await client.put(
        f"/api/media/{media['id']}/position",
        headers=headers,
        json={"position_seconds": 276.1},
    )

    assert saved.status_code == 200
    assert saved.json()["position_seconds"] == 275.5
    assert outside.status_code == 422
