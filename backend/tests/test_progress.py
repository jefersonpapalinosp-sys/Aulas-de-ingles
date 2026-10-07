"""Tentativas, progresso e isolamento entre contas."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def conta(client: AsyncClient, sufixo: str) -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={
            "email": f"{sufixo}@exemplo.com",
            "password": "senha-bem-grande",
            "display_name": sufixo,
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def primeiro_exercicio(client: AsyncClient, aula: int = 31) -> dict[str, object]:
    itens = (await client.get(f"/api/exercises?lesson={aula}")).json()
    return itens[0]


@pytest.mark.asyncio
async def test_tentativa_exige_login(client: AsyncClient) -> None:
    ex = await primeiro_exercicio(client)
    r = await client.post(f"/api/exercises/{ex['id']}/attempt", json={"answer": "faster"})
    assert r.status_code == 401
    assert (await client.get(f"/api/exercises/{ex['id']}/answer")).status_code == 401
    assert (await client.get("/api/me/progress")).status_code == 401
    assert (await client.put("/api/lessons/31/studied")).status_code == 401


@pytest.mark.asyncio
async def test_correcao_acontece_no_servidor(client: AsyncClient) -> None:
    """Exercício 1 da aula 31: 'A bicycle is ____ (fast) than a taxi.'"""
    h = await conta(client, "corrige")
    ex = await primeiro_exercicio(client)

    certo = await client.post(
        f"/api/exercises/{ex['id']}/attempt", json={"answer": "Faster."}, headers=h
    )
    assert certo.status_code == 200
    assert certo.json()["correct"] is True
    assert certo.json()["explanation"]

    errado = await client.post(
        f"/api/exercises/{ex['id']}/attempt", json={"answer": "more fast"}, headers=h
    )
    assert errado.json()["correct"] is False
    # Errar não entrega o gabarito de brinde.
    assert "faster" not in errado.text.lower()


@pytest.mark.asyncio
async def test_tentativa_errada_fica_gravada_com_o_que_foi_digitado(client: AsyncClient) -> None:
    h = await conta(client, "grava")
    ex = await primeiro_exercicio(client)
    await client.post(f"/api/exercises/{ex['id']}/attempt", json={"answer": "more fast"}, headers=h)

    p = (await client.get("/api/me/progress", headers=h)).json()
    aula31 = next(linha for linha in p["lessons"] if linha["lesson_number"] == 31)
    assert aula31["attempts"] == 1
    assert aula31["correct"] == 0


@pytest.mark.asyncio
async def test_gabarito_so_sai_quando_pedido(client: AsyncClient) -> None:
    h = await conta(client, "gabarito")
    itens = (await client.get("/api/exercises?lesson=31")).json()
    ex = next(e for e in itens if e["position"] == 3)
    r = await client.get(f"/api/exercises/{ex['id']}/answer", headers=h)
    assert r.status_code == 200
    assert set(r.json()["answers"]) == {"should", "ought to"}


@pytest.mark.asyncio
async def test_exercicio_inexistente_devolve_404(client: AsyncClient) -> None:
    h = await conta(client, "quatrocentos")
    r = await client.post("/api/exercises/99999/attempt", json={"answer": "x"}, headers=h)
    assert r.status_code == 404
    assert (await client.get("/api/exercises/99999/answer", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_marcar_aula_e_idempotente(client: AsyncClient) -> None:
    h = await conta(client, "marca")
    for _ in range(3):
        assert (await client.put("/api/lessons/33/studied", headers=h)).status_code == 204

    p = (await client.get("/api/me/progress", headers=h)).json()
    assert p["studied_count"] == 1
    assert p["total_lessons"] == 10
    assert [linha["studied"] for linha in p["lessons"]].count(True) == 1


@pytest.mark.asyncio
async def test_desmarcar_aula(client: AsyncClient) -> None:
    h = await conta(client, "desmarca")
    await client.put("/api/lessons/33/studied", headers=h)
    assert (await client.delete("/api/lessons/33/studied", headers=h)).status_code == 204
    assert (await client.get("/api/me/progress", headers=h)).json()["studied_count"] == 0
    # Desmarcar o que não está marcado não é erro.
    assert (await client.delete("/api/lessons/33/studied", headers=h)).status_code == 204


@pytest.mark.asyncio
async def test_progresso_traz_as_dez_aulas_mesmo_sem_atividade(client: AsyncClient) -> None:
    h = await conta(client, "zerado")
    p = (await client.get("/api/me/progress", headers=h)).json()
    assert len(p["lessons"]) == 10
    assert p == {
        **p,
        "studied_count": 0,
        "attempts": 0,
        "correct": 0,
    }
    assert all(linha["studied_at"] is None for linha in p["lessons"])


@pytest.mark.asyncio
async def test_duas_contas_nao_veem_o_progresso_uma_da_outra(client: AsyncClient) -> None:
    ex = await primeiro_exercicio(client)
    ana = await conta(client, "ana")

    # Um segundo cliente, para não compartilhar o cookie de refresh.
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as outro:
        bruno = await conta(outro, "bruno")

        await client.put("/api/lessons/31/studied", headers=ana)
        await client.post(
            f"/api/exercises/{ex['id']}/attempt", json={"answer": "faster"}, headers=ana
        )

        p_ana = (await client.get("/api/me/progress", headers=ana)).json()
        p_bruno = (await outro.get("/api/me/progress", headers=bruno)).json()

    assert p_ana["studied_count"] == 1
    assert p_ana["attempts"] == 1
    assert p_bruno["studied_count"] == 0
    assert p_bruno["attempts"] == 0


@pytest.mark.asyncio
async def test_progresso_sobrevive_a_outro_navegador(client: AsyncClient) -> None:
    """Marcar num lugar e abrir em outro mostra a mesma marcação.

    É o critério de aceite da sprint: o progresso parou de morar no navegador.
    Dois clientes HTTP diferentes = dois navegadores; o que os liga é a conta.
    """
    h = await conta(client, "doisnavegadores")
    await client.put("/api/lessons/38/studied", headers=h)

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as outro_navegador:
        entrou = await outro_navegador.post(
            "/api/auth/login",
            json={"email": "doisnavegadores@exemplo.com", "password": "senha-bem-grande"},
        )
        h2 = {"Authorization": f"Bearer {entrou.json()['access_token']}"}
        p = (await outro_navegador.get("/api/me/progress", headers=h2)).json()

    assert next(linha for linha in p["lessons"] if linha["lesson_number"] == 38)["studied"] is True
