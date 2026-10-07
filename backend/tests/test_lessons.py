"""Leitura do conteúdo — contra o Postgres do compose, já semeado."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_lista_as_dez_aulas_em_ordem(client: AsyncClient) -> None:
    r = await client.get("/api/lessons")
    assert r.status_code == 200
    aulas = r.json()
    assert [a["number"] for a in aulas] == list(range(31, 41))
    assert aulas[0]["title"] == "Take Me Out to the Ball Game"
    # O resumo não carrega a aula inteira.
    assert "grammar_blocks" not in aulas[0]


@pytest.mark.asyncio
async def test_aula_31_tem_o_conteudo_esperado(client: AsyncClient) -> None:
    r = await client.get("/api/lessons/31")
    assert r.status_code == 200
    a = r.json()
    assert len(a["grammar_blocks"]) == 3
    assert len(a["phrases"]) == 6
    assert len(a["vocab"]) == 11
    assert len(a["exercises"]) == 6
    assert len(a["goals"]) == 4
    assert all(isinstance(g, str) for g in a["goals"])


@pytest.mark.asyncio
async def test_aula_inexistente_devolve_404(client: AsyncClient) -> None:
    r = await client.get("/api/lessons/99")
    assert r.status_code == 404
    assert "99" in r.json()["detail"]


@pytest.mark.asyncio
async def test_resposta_certa_nao_vaza_no_contrato(client: AsyncClient) -> None:
    """Na S3 a correção vai para o servidor; o contrato já nasce sem a resposta."""
    r = await client.get("/api/lessons/34")
    assert "answers" not in r.text
    for exercicio in r.json()["exercises"]:
        assert set(exercicio) == {"id", "position", "prompt", "hint", "explanation"}


@pytest.mark.asyncio
async def test_ordem_interna_respeita_position(client: AsyncClient) -> None:
    a = (await client.get("/api/lessons/33")).json()
    assert [e["position"] for e in a["exercises"]] == sorted(e["position"] for e in a["exercises"])
    primeiro = a["grammar_blocks"][0]
    assert primeiro["heading"].startswith("Verbo + -er")


@pytest.mark.asyncio
async def test_bloco_gramatical_traz_cabecalho_e_linhas(client: AsyncClient) -> None:
    bloco = (await client.get("/api/lessons/31")).json()["grammar_blocks"][0]
    assert bloco["table_head"] == ["Adjetivo", "Comparativo", "Frase da aula"]
    assert len(bloco["rows"][0]["cells"]) == len(bloco["table_head"])
    assert bloco["warning"] is not None


@pytest.mark.asyncio
async def test_texto_vem_em_markdown_sem_html(client: AsyncClient) -> None:
    """Contrato de formato: Markdown no banco, nunca HTML cru."""
    corpo = (await client.get("/api/lessons/31")).text
    for tag in ("<b>", "<i>", "<code>", "<span", "&mdash;", "&rarr;"):
        assert tag not in corpo, f"vazou {tag} no payload"
    bloco = (await client.get("/api/lessons/31")).json()["grammar_blocks"][0]
    assert "**" in bloco["rows"][0]["cells"][1]


@pytest.mark.asyncio
async def test_vocabulario_filtra_por_aula(client: AsyncClient) -> None:
    todos = (await client.get("/api/vocab")).json()
    assert len(todos) == 115
    da_40 = (await client.get("/api/vocab?lesson=40")).json()
    assert len(da_40) == 13
    assert {v["lesson_number"] for v in da_40} == {40}
    assert da_40[0]["term"] == "the woods"
    assert da_40[0]["ipa"].startswith("/")


@pytest.mark.asyncio
async def test_vocabulario_de_aula_inexistente_vem_vazio(client: AsyncClient) -> None:
    assert (await client.get("/api/vocab?lesson=99")).json() == []


@pytest.mark.asyncio
async def test_exercicios_do_bloco_inteiro(client: AsyncClient) -> None:
    todos = (await client.get("/api/exercises")).json()
    assert len(todos) == 62
    assert {e["lesson_number"] for e in todos} == set(range(31, 41))
    # Ordenado por aula e depois por posição.
    chaves = [(e["lesson_number"], e["position"]) for e in todos]
    assert chaves == sorted(chaves)
    # A resposta certa continua fora do contrato.
    assert "answers" not in (await client.get("/api/exercises")).text


@pytest.mark.asyncio
async def test_exercicios_filtra_por_aula(client: AsyncClient) -> None:
    da_39 = (await client.get("/api/exercises?lesson=39")).json()
    assert len(da_39) == 7
    assert {e["lesson_number"] for e in da_39} == {39}


@pytest.mark.asyncio
async def test_correcao_acontece_no_servidor(client: AsyncClient) -> None:
    """Exercício 1 da aula 31: 'A bicycle is ____ (fast) than a taxi.'"""
    ex = (await client.get("/api/exercises?lesson=31")).json()[0]

    certo = await client.post(f"/api/exercises/{ex['id']}/check", json={"answer": "Faster."})
    assert certo.status_code == 200
    assert certo.json()["correct"] is True
    assert certo.json()["explanation"]

    errado = await client.post(f"/api/exercises/{ex['id']}/check", json={"answer": "more fast"})
    assert errado.json()["correct"] is False
    # Errar não entrega o gabarito de brinde.
    assert "faster" not in errado.text.lower()


@pytest.mark.asyncio
async def test_gabarito_so_sai_quando_pedido(client: AsyncClient) -> None:
    ex = [e for e in (await client.get("/api/exercises?lesson=31")).json() if e["position"] == 3][0]
    r = await client.get(f"/api/exercises/{ex['id']}/answer")
    assert r.status_code == 200
    assert set(r.json()["answers"]) == {"should", "ought to"}


@pytest.mark.asyncio
async def test_exercicio_inexistente_devolve_404(client: AsyncClient) -> None:
    assert (await client.post("/api/exercises/99999/check", json={"answer": "x"})).status_code == 404
    assert (await client.get("/api/exercises/99999/answer")).status_code == 404
