"""Deck de revisão: semeadura, agendamento e isolamento."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReviewItem


def tentativa(answer: str, key: int = 1) -> dict[str, str]:
    return {
        "answer": answer,
        "idempotency_key": f"10000000-0000-4000-8000-{key:012d}",
    }


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


@pytest.mark.asyncio
async def test_deck_exige_login(client: AsyncClient) -> None:
    assert (await client.get("/api/review/due")).status_code == 401
    assert (await client.get("/api/review/summary")).status_code == 401
    assert (await client.post("/api/review/1/grade", json={"quality": 4})).status_code == 401


@pytest.mark.asyncio
async def test_marcar_aula_estudada_semeia_o_vocabulario(client: AsyncClient) -> None:
    """Aula 40 tem 13 itens de vocabulário."""
    h = await conta(client, "semeia")
    await client.put("/api/lessons/40/studied", headers=h)

    resumo = (await client.get("/api/review/summary", headers=h)).json()
    assert resumo["total_cards"] == 13
    # Carta nova nasce vencida: entra na revisão de hoje.
    assert resumo["due_now"] == 13


@pytest.mark.asyncio
async def test_marcar_de_novo_nao_duplica_nem_reinicia(client: AsyncClient) -> None:
    h = await conta(client, "naodup")
    await client.put("/api/lessons/40/studied", headers=h)

    carta = (await client.get("/api/review/due?limit=1", headers=h)).json()[0]
    await client.post(f"/api/review/{carta['id']}/grade", json={"quality": 5}, headers=h)

    # Marcar de novo não pode trazer a carta avaliada de volta para hoje.
    await client.put("/api/lessons/40/studied", headers=h)
    resumo = (await client.get("/api/review/summary", headers=h)).json()
    assert resumo["total_cards"] == 13
    assert resumo["due_now"] == 12


@pytest.mark.asyncio
async def test_errar_exercicio_de_vocabulario_poe_a_palavra_no_deck(client: AsyncClient) -> None:
    """Aula 39, exercício 2: a resposta certa é o termo 'dishonest'."""
    h = await conta(client, "errou")
    exercicios = (await client.get("/api/exercises?lesson=39")).json()
    ex = next(e for e in exercicios if "honest" in e["prompt"])

    await client.post(f"/api/exercises/{ex['id']}/attempt", json=tentativa("nada"), headers=h)

    cartas = (await client.get("/api/review/due", headers=h)).json()
    assert [c["prompt"] for c in cartas] == ["dishonest"]


@pytest.mark.asyncio
async def test_acertar_nao_poe_nada_no_deck(client: AsyncClient) -> None:
    h = await conta(client, "acertou")
    exercicios = (await client.get("/api/exercises?lesson=39")).json()
    ex = next(e for e in exercicios if "honest" in e["prompt"])

    await client.post(f"/api/exercises/{ex['id']}/attempt", json=tentativa("dishonest"), headers=h)
    assert (await client.get("/api/review/summary", headers=h)).json()["total_cards"] == 0


@pytest.mark.asyncio
async def test_adicionar_item_avulso_e_idempotente(client: AsyncClient) -> None:
    h = await conta(client, "avulso")
    item = (await client.get("/api/vocab?lesson=31")).json()[0]

    primeiro = (await client.post(f"/api/review/items/{item['id']}", headers=h)).json()
    assert primeiro == {
        "due_now": 1,
        "total_cards": 1,
        "suspended": 0,
        "by_type": {"vocabulary": 1},
        "added": 1,
    }

    segundo = (await client.post(f"/api/review/items/{item['id']}", headers=h)).json()
    assert segundo == {
        "due_now": 1,
        "total_cards": 1,
        "suspended": 0,
        "by_type": {"vocabulary": 1},
        "added": 0,
    }


@pytest.mark.asyncio
async def test_avaliar_tira_a_carta_do_deck_de_hoje(client: AsyncClient) -> None:
    h = await conta(client, "avalia")
    await client.post("/api/review/lessons/36", headers=h)

    antes = (await client.get("/api/review/due", headers=h)).json()
    carta = antes[0]

    r = await client.post(f"/api/review/{carta['id']}/grade", json={"quality": 4}, headers=h)
    assert r.status_code == 200
    novo = r.json()
    assert novo["interval_days"] == 1
    assert novo["repetitions"] == 1

    depois = (await client.get("/api/review/due", headers=h)).json()
    assert carta["id"] not in [c["id"] for c in depois]
    assert len(depois) == len(antes) - 1

    # E o próximo vencimento está um dia à frente.
    proxima = datetime.fromisoformat(novo["due_at"])
    assert timedelta(hours=23) < proxima - datetime.now(UTC) < timedelta(hours=25)


@pytest.mark.asyncio
async def test_errar_na_revisao_mantem_a_carta_para_amanha(client: AsyncClient) -> None:
    h = await conta(client, "lapso")
    await client.post("/api/review/lessons/36", headers=h)
    carta = (await client.get("/api/review/due?limit=1", headers=h)).json()[0]

    novo = (
        await client.post(f"/api/review/{carta['id']}/grade", json={"quality": 1}, headers=h)
    ).json()
    assert novo["lapses"] == 1
    assert novo["repetitions"] == 0
    assert novo["interval_days"] == 1
    assert novo["ease_factor"] < 2.5


@pytest.mark.asyncio
async def test_nota_fora_da_faixa_e_recusada(client: AsyncClient) -> None:
    h = await conta(client, "faixa")
    await client.post("/api/review/lessons/36", headers=h)
    carta = (await client.get("/api/review/due?limit=1", headers=h)).json()[0]
    r = await client.post(f"/api/review/{carta['id']}/grade", json={"quality": 9}, headers=h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_carta_de_outra_pessoa_e_404(client: AsyncClient, session: AsyncSession) -> None:
    """Dizer 'existe, mas não é sua' já conta quantas cartas os outros têm."""
    ana = await conta(client, "dona")
    await client.post("/api/review/lessons/36", headers=ana)
    dela = (await client.get("/api/review/due?limit=1", headers=ana)).json()[0]

    bruno = await conta(client, "intruso")
    r = await client.post(f"/api/review/{dela['id']}/grade", json={"quality": 5}, headers=bruno)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_deck_so_traz_carta_vencida(client: AsyncClient, session: AsyncSession) -> None:
    h = await conta(client, "vencida")
    await client.post("/api/review/lessons/36", headers=h)

    # Empurra todas para daqui a uma semana.
    cartas = list((await session.execute(select(ReviewItem))).scalars())
    for c in cartas:
        c.due_at = datetime.now(UTC) + timedelta(days=7)
    await session.commit()

    assert (await client.get("/api/review/due", headers=h)).json() == []
    assert (await client.get("/api/review/summary", headers=h)).json()["due_now"] == 0

    # Uma única volta a vencer.
    cartas[0].due_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.commit()
    assert len((await client.get("/api/review/due", headers=h)).json()) == 1


@pytest.mark.asyncio
async def test_due_at_e_utc_independente_do_fuso_do_processo(client: AsyncClient) -> None:
    """O fuso do processo não pode vazar para o banco.

    Roda igual sob TZ=UTC, America/Sao_Paulo ou Pacific/Kiritimati (UTC+14).
    """
    h = await conta(client, "fuso")
    await client.post("/api/review/lessons/36", headers=h)
    carta = (await client.get("/api/review/due?limit=1", headers=h)).json()[0]

    novo = (
        await client.post(f"/api/review/{carta['id']}/grade", json={"quality": 4}, headers=h)
    ).json()
    proxima = datetime.fromisoformat(novo["due_at"])
    assert proxima.tzinfo is not None, "due_at precisa chegar com fuso"
    assert proxima.utcoffset() == timedelta(0), "o banco guarda UTC"


@pytest.mark.asyncio
async def test_progresso_mostra_o_deck(client: AsyncClient) -> None:
    h = await conta(client, "contador")
    await client.put("/api/lessons/36/studied", headers=h)
    p = (await client.get("/api/me/progress", headers=h)).json()
    assert p["review_cards"] == 11
    assert p["review_due"] == 11


@pytest.mark.asyncio
async def test_erro_gramatical_gera_um_item_sem_duplicar(client: AsyncClient) -> None:
    headers = await conta(client, "erro-gramatical")
    exercise = (await client.get("/api/exercises?lesson=31")).json()[0]

    for key, answer in ((301, "more fast"), (302, "fastest")):
        response = await client.post(
            f"/api/exercises/{exercise['id']}/attempt",
            headers=headers,
            json=tentativa(answer, key),
        )
        assert response.status_code == 200

    items = (await client.get("/api/review/due", headers=headers)).json()
    assert len(items) == 1
    assert items[0]["item_type"] == "grammar_error"
    assert items[0]["skill"] == "grammar"
    assert "resposta incorreta" in items[0]["reason"]
    assert items[0]["prompt_note"].endswith("fastest")


@pytest.mark.asyncio
async def test_filtros_encontram_listening_por_tipo_competencia_e_duracao(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "filtros")
    exercises = (await client.get("/api/exercises?lesson=31")).json()
    dictation = next(item for item in exercises if item["position"] == 7)
    await client.post(
        f"/api/exercises/{dictation['id']}/attempt",
        headers=headers,
        json=tentativa("wrong sentence", 401),
    )

    matching = await client.get(
        "/api/review/due?item_type=listening&skill=listening&max_minutes=2",
        headers=headers,
    )
    excluded = await client.get(
        "/api/review/due?item_type=grammar_error",
        headers=headers,
    )
    assert matching.status_code == 200
    assert [item["item_type"] for item in matching.json()] == ["listening"]
    assert excluded.json() == []


@pytest.mark.asyncio
async def test_due_e_items_filtram_curso_unidade_e_expoem_identidade(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "escopo-curricular")
    await client.post("/api/review/lessons/31", headers=headers)
    await client.post("/api/review/lessons/41", headers=headers)

    first = (
        await client.get(
            "/api/review/due?course=voa-level-1&unit=31-40", headers=headers
        )
    ).json()
    second = (
        await client.get(
            "/api/review/due?course=voa-level-1&unit=40-44", headers=headers
        )
    ).json()
    assert first and second
    for unit_slug, lesson_number, items in (
        ("31-40", 31, first),
        ("40-44", 41, second),
    ):
        assert {item["lesson_number"] for item in items} == {lesson_number}
        assert all(item["course_slug"] == "voa-level-1" for item in items)
        assert all(
            item["course_title"] == "Let's Learn English — Level 1" for item in items
        )
        assert all(item["unit_slug"] == unit_slug for item in items)
        assert all(item["lesson_title"] for item in items)

    assert (
        await client.get(
            "/api/review/due?course=voa-level-2&unit=31-40", headers=headers
        )
    ).json() == []

    for item in (first[0], second[0]):
        response = await client.patch(
            f"/api/review/{item['id']}",
            headers=headers,
            json={"status": "suspended"},
        )
        assert response.status_code == 200

    suspended_first = (
        await client.get(
            "/api/review/items?status=suspended&course=voa-level-1&unit=31-40",
            headers=headers,
        )
    ).json()
    suspended_second = (
        await client.get(
            "/api/review/items?status=suspended&course=voa-level-1&unit=40-44",
            headers=headers,
        )
    ).json()
    assert [item["id"] for item in suspended_first] == [first[0]["id"]]
    assert [item["id"] for item in suspended_second] == [second[0]["id"]]
    assert suspended_first[0]["unit_slug"] == "31-40"
    assert suspended_second[0]["unit_slug"] == "40-44"


@pytest.mark.asyncio
async def test_item_pode_ser_suspenso_reativado_e_excluido(client: AsyncClient) -> None:
    owner = await conta(client, "gerencia")
    await client.post("/api/review/lessons/31", headers=owner)
    item = (await client.get("/api/review/due?limit=1", headers=owner)).json()[0]

    suspended = await client.patch(
        f"/api/review/{item['id']}", headers=owner, json={"status": "suspended"}
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"
    due_after_suspend = (await client.get("/api/review/due", headers=owner)).json()
    assert item["id"] not in [row["id"] for row in due_after_suspend]
    listed = (await client.get("/api/review/items?status=suspended", headers=owner)).json()
    assert [row["id"] for row in listed] == [item["id"]]
    assert (
        await client.post(f"/api/review/{item['id']}/grade", headers=owner, json={"quality": 4})
    ).status_code == 409

    intruder = await conta(client, "gerencia-intruso")
    assert (
        await client.patch(f"/api/review/{item['id']}", headers=intruder, json={"status": "active"})
    ).status_code == 404

    reactivated = await client.patch(
        f"/api/review/{item['id']}", headers=owner, json={"status": "active"}
    )
    assert reactivated.json()["status"] == "active"
    assert (await client.delete(f"/api/review/{item['id']}", headers=owner)).status_code == 204
    assert (
        await client.patch(f"/api/review/{item['id']}", headers=owner, json={"status": "active"})
    ).status_code == 404


@pytest.mark.asyncio
async def test_tipo_dificil_encurta_o_intervalo_sem_mudar_sm2(client: AsyncClient) -> None:
    headers = await conta(client, "intervalo-tipo")
    exercise = (await client.get("/api/exercises?lesson=31")).json()[0]
    await client.post(
        f"/api/exercises/{exercise['id']}/attempt",
        headers=headers,
        json=tentativa("more fast", 501),
    )
    item = (await client.get("/api/review/due", headers=headers)).json()[0]

    first = await client.post(
        f"/api/review/{item['id']}/grade", headers=headers, json={"quality": 4}
    )
    second = await client.post(
        f"/api/review/{item['id']}/grade", headers=headers, json={"quality": 4}
    )
    assert first.json()["interval_days"] == 1
    assert second.json()["interval_days"] == 5  # base SM-2 6 × fator 0,8
