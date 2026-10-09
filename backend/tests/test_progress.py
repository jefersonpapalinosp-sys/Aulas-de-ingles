"""Tentativas, progresso e isolamento entre contas."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Course, CourseUnit, Lesson
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


def tentativa(answer: str, key: int = 1) -> dict[str, str]:
    return {
        "answer": answer,
        "idempotency_key": f"00000000-0000-4000-8000-{key:012d}",
    }


@pytest.mark.asyncio
async def test_tentativa_exige_login(client: AsyncClient) -> None:
    ex = await primeiro_exercicio(client)
    r = await client.post(f"/api/exercises/{ex['id']}/attempt", json=tentativa("faster"))
    assert r.status_code == 401
    assert (await client.get(f"/api/exercises/{ex['id']}/answer")).status_code == 401
    assert (await client.get(f"/api/exercises/{ex['id']}/hints/1")).status_code == 401
    assert (await client.get("/api/me/progress")).status_code == 401
    assert (await client.put("/api/lessons/31/studied")).status_code == 401
    assert (await client.get("/api/lessons/31/study-session")).status_code == 401
    assert (
        await client.put(
            "/api/lessons/31/study-session",
            json={"current_step": "assistir", "completed_steps": ["preparar"]},
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_jornada_guiada_salva_e_normaliza_as_etapas(client: AsyncClient) -> None:
    h = await conta(client, "jornada")
    initial_response = await client.get("/api/lessons/31/study-session", headers=h)
    inicial = initial_response.json()
    assert initial_response.headers["cache-control"] == "private, no-store"
    assert inicial == {
        "lesson_number": 31,
        "current_step": "preparar",
        "completed_steps": [],
        "started_at": None,
        "updated_at": None,
        "completed_at": None,
        "total_seconds": 0,
    }

    salvo = await client.put(
        "/api/lessons/31/study-session",
        headers=h,
        json={
            "current_step": "praticar",
            "completed_steps": ["estudar", "preparar", "assistir", "preparar"],
        },
    )
    assert salvo.status_code == 200
    assert salvo.json()["completed_steps"] == ["preparar", "assistir", "estudar"]
    assert salvo.json()["updated_at"] is not None

    retomada = (await client.get("/api/lessons/31/study-session", headers=h)).json()
    assert retomada["current_step"] == "praticar"
    assert retomada["completed_steps"] == ["preparar", "assistir", "estudar"]


@pytest.mark.asyncio
async def test_rotas_canonicas_e_progresso_contextual_por_curso(client: AsyncClient) -> None:
    headers = await conta(client, "curso-canonico")
    base = "/api/courses/voa-level-1/lessons/32"

    assert (await client.put(f"{base}/studied", headers=headers)).status_code == 204
    saved = await client.put(
        f"{base}/study-session",
        headers=headers,
        json={"current_step": "assistir", "completed_steps": ["preparar"]},
    )
    resumed = await client.get(f"{base}/study-session", headers=headers)
    level_1 = await client.get("/api/me/progress?course=voa-level-1", headers=headers)
    level_2 = await client.get("/api/me/progress?course=voa-level-2", headers=headers)

    assert saved.status_code == resumed.status_code == 200
    assert resumed.headers["cache-control"] == "private, no-store"
    assert level_1.headers["cache-control"] == "private, no-store"
    assert level_2.headers["cache-control"] == "private, no-store"
    assert resumed.json()["current_step"] == "assistir"
    assert level_1.json()["total_lessons"] == 22
    assert level_1.json()["studied_count"] == 1
    row = next(item for item in level_1.json()["lessons"] if item["lesson_number"] == 32)
    assert row["course_slug"] == "voa-level-1"
    assert row["unit_slug"] == "31-40"
    assert level_2.json()["total_lessons"] == 25
    assert level_2.json()["studied_count"] == 0
    assert {item["lesson_number"] for item in level_2.json()["lessons"]} == set(range(1, 26))
    assert all(item["course_slug"] == "voa-level-2" for item in level_2.json()["lessons"])


@pytest.mark.asyncio
async def test_aula_um_em_dois_cursos_mantem_sessoes_e_historico_distintos(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "mesmo-numero-historico")
    level_1 = (
        await session.execute(select(Course).where(Course.slug == "voa-level-1"))
    ).scalar_one()
    unit = (
        await session.execute(
            select(CourseUnit).where(
                CourseUnit.course_id == level_1.id,
                CourseUnit.slug == "31-40",
            )
        )
    ).scalar_one()
    level_1_lesson = Lesson(
        course_id=level_1.id,
        unit_id=unit.id,
        number=1,
        slug="history-level-1-lesson-1",
        position=100,
        title="Level 1 lesson one",
        title_pt="Aula um do Level 1",
        voa_url="https://example.com/level-1/1",
        grammar_tag="Fixture",
        focus_points=[],
        lead="Fixture.",
        warmup_prompt="Teste.",
        listening_focus="Teste.",
    )
    session.add(level_1_lesson)
    await session.commit()

    try:
        level_1_path = "/api/courses/voa-level-1/lessons/1/study-session"
        level_2_path = "/api/courses/voa-level-2/lessons/1/study-session"
        assert (
            await client.put(
                level_1_path,
                headers=headers,
                json={"current_step": "assistir", "completed_steps": ["preparar"]},
            )
        ).status_code == 200
        assert (
            await client.put(
                level_2_path,
                headers=headers,
                json={
                    "current_step": "praticar",
                    "completed_steps": ["preparar", "assistir", "estudar"],
                },
            )
        ).status_code == 200

        level_1_state = (await client.get(level_1_path, headers=headers)).json()
        level_2_state = (await client.get(level_2_path, headers=headers)).json()
        assert level_1_state["current_step"] == "assistir"
        assert level_2_state["current_step"] == "praticar"
        assert level_1_state["completed_steps"] == ["preparar"]
        assert level_2_state["completed_steps"] == [
            "preparar",
            "assistir",
            "estudar",
        ]
    finally:
        await session.execute(delete(Lesson).where(Lesson.id == level_1_lesson.id))
        await session.commit()


@pytest.mark.asyncio
async def test_progresso_filtra_curso_unidade_tentativas_e_revisao(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "progresso-por-unidade")
    exercise_31 = await primeiro_exercicio(client, 31)
    exercise_41 = await primeiro_exercicio(client, 41)

    await client.put("/api/lessons/31/studied", headers=headers)
    await client.put("/api/lessons/41/studied", headers=headers)
    await client.post(
        f"/api/exercises/{exercise_31['id']}/attempt",
        headers=headers,
        json=tentativa("wrong", 901),
    )
    await client.post(
        f"/api/exercises/{exercise_41['id']}/attempt",
        headers=headers,
        json=tentativa("wrong", 902),
    )

    first = (
        await client.get("/api/me/progress?course=voa-level-1&unit=31-40", headers=headers)
    ).json()
    second = (
        await client.get("/api/me/progress?course=voa-level-1&unit=40-44", headers=headers)
    ).json()
    third = (
        await client.get("/api/me/progress?course=voa-level-1&unit=45-49", headers=headers)
    ).json()

    assert first["total_lessons"] == 10
    assert first["studied_count"] == first["attempts"] == 1
    assert {item["lesson_number"] for item in first["lessons"]} == set(range(31, 41))
    assert all(item["course_slug"] == "voa-level-1" for item in first["lessons"])
    assert all(item["unit_slug"] == "31-40" for item in first["lessons"])

    assert second["total_lessons"] == 4
    assert second["studied_count"] == second["attempts"] == 1
    assert {item["lesson_number"] for item in second["lessons"]} == set(range(41, 45))
    assert all(item["unit_slug"] == "40-44" for item in second["lessons"])

    assert third["total_lessons"] == 5
    assert third["studied_count"] == third["attempts"] == 0
    assert {item["lesson_number"] for item in third["lessons"]} == set(range(45, 50))
    assert all(item["unit_slug"] == "45-49" for item in third["lessons"])

    for unit_slug, progress in (("31-40", first), ("40-44", second), ("45-49", third)):
        due = (
            await client.get(
                f"/api/review/due?course=voa-level-1&unit={unit_slug}",
                headers=headers,
            )
        ).json()
        assert progress["review_cards"] == progress["review_due"] == len(due)

    other_course = (
        await client.get("/api/me/progress?course=voa-level-2&unit=45-49", headers=headers)
    ).json()
    assert other_course["total_lessons"] == 0
    assert other_course["studied_count"] == other_course["attempts"] == 0
    assert other_course["review_cards"] == other_course["review_due"] == 0
    assert other_course["lessons"] == []

    ambiguous = await client.get("/api/me/progress?unit=31-40", headers=headers)
    assert ambiguous.status_code == 422


@pytest.mark.asyncio
async def test_progresso_ignora_curso_e_unidade_nao_publicados(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "progresso-publicado")
    assert (
        await client.put("/api/courses/voa-level-2/lessons/1/studied", headers=headers)
    ).status_code == 204

    course = (
        await session.execute(select(Course).where(Course.slug == "voa-level-2"))
    ).scalar_one()
    unit = (
        await session.execute(
            select(CourseUnit).where(
                CourseUnit.course_id == course.id,
                CourseUnit.slug == "1-5",
            )
        )
    ).scalar_one()
    original_course_status = course.status
    original_unit_status = unit.status

    try:
        baseline = await client.get("/api/me/progress?course=voa-level-2", headers=headers)
        assert baseline.headers["cache-control"] == "private, no-store"
        assert baseline.json()["total_lessons"] == 25
        assert baseline.json()["studied_count"] == 1
        assert baseline.json()["review_cards"] > 0

        unit.status = "planned"
        await session.commit()
        hidden_unit = (
            await client.get("/api/me/progress?course=voa-level-2", headers=headers)
        ).json()
        assert hidden_unit["review_due"] == hidden_unit["review_cards"] == 0
        assert hidden_unit["studied_count"] == hidden_unit["attempts"] == 0
        assert hidden_unit["correct"] == 0
        assert hidden_unit["total_lessons"] == 20
        assert {item["lesson_number"] for item in hidden_unit["lessons"]} == set(range(6, 26))

        hidden_unit_scope = (
            await client.get("/api/me/progress?course=voa-level-2&unit=1-5", headers=headers)
        ).json()
        assert hidden_unit_scope["total_lessons"] == 0
        assert hidden_unit_scope["lessons"] == []

        unit.status = "published"
        course.status = "planned"
        await session.commit()
        hidden_course = (
            await client.get("/api/me/progress?course=voa-level-2", headers=headers)
        ).json()
        assert hidden_course == {
            "review_due": 0,
            "review_cards": 0,
            "studied_count": 0,
            "total_lessons": 0,
            "attempts": 0,
            "correct": 0,
            "lessons": [],
        }
    finally:
        course.status = original_course_status
        unit.status = original_unit_status
        await session.commit()


@pytest.mark.asyncio
async def test_jornada_e_isolada_por_conta_e_valida_etapa(client: AsyncClient) -> None:
    ana = await conta(client, "jornada-ana")
    await client.put(
        "/api/lessons/31/study-session",
        headers=ana,
        json={"current_step": "assistir", "completed_steps": ["preparar"]},
    )

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as outro:
        bruno = await conta(outro, "jornada-bruno")
        estado = (await outro.get("/api/lessons/31/study-session", headers=bruno)).json()
        invalido = await outro.put(
            "/api/lessons/31/study-session",
            headers=bruno,
            json={"current_step": "inexistente", "completed_steps": []},
        )

    assert estado["current_step"] == "preparar"
    assert estado["updated_at"] is None
    assert invalido.status_code == 422


@pytest.mark.asyncio
async def test_correcao_acontece_no_servidor(client: AsyncClient) -> None:
    """Exercício 1 da aula 31: 'A bicycle is ____ (fast) than a taxi.'"""
    h = await conta(client, "corrige")
    ex = await primeiro_exercicio(client)

    certo = await client.post(
        f"/api/exercises/{ex['id']}/attempt", json=tentativa("Faster."), headers=h
    )
    assert certo.status_code == 200
    assert certo.json()["correct"] is True
    assert certo.json()["explanation"]

    errado = await client.post(
        f"/api/exercises/{ex['id']}/attempt", json=tentativa("more fast", 2), headers=h
    )
    assert errado.json()["correct"] is False
    assert errado.json()["explanation"] is None
    assert errado.json()["feedback"]["category"] == "extra_word"
    assert errado.json()["feedback"]["message"]
    # Errar não entrega o gabarito de brinde.
    assert "faster" not in errado.text.lower()


@pytest.mark.asyncio
async def test_tentativa_errada_fica_gravada_com_o_que_foi_digitado(client: AsyncClient) -> None:
    h = await conta(client, "grava")
    ex = await primeiro_exercicio(client)
    await client.post(f"/api/exercises/{ex['id']}/attempt", json=tentativa("more fast"), headers=h)

    p = (await client.get("/api/me/progress", headers=h)).json()
    aula31 = next(linha for linha in p["lessons"] if linha["lesson_number"] == 31)
    assert aula31["attempts"] == 1
    assert aula31["correct"] == 0


@pytest.mark.asyncio
async def test_gabarito_so_sai_quando_pedido(client: AsyncClient) -> None:
    h = await conta(client, "gabarito")
    itens = (await client.get("/api/exercises?lesson=31")).json()
    ex = next(e for e in itens if e["position"] == 4)
    r = await client.get(f"/api/exercises/{ex['id']}/answer", headers=h)
    assert r.status_code == 200
    assert set(r.json()["answers"]) == {"a lot", "much", "far"}


@pytest.mark.asyncio
async def test_exercicio_inexistente_devolve_404(client: AsyncClient) -> None:
    h = await conta(client, "quatrocentos")
    r = await client.post("/api/exercises/99999/attempt", json=tentativa("x"), headers=h)
    assert r.status_code == 404
    assert (await client.get("/api/exercises/99999/answer", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_marcar_aula_e_idempotente(client: AsyncClient) -> None:
    h = await conta(client, "marca")
    for _ in range(3):
        assert (await client.put("/api/lessons/33/studied", headers=h)).status_code == 204

    p = (await client.get("/api/me/progress", headers=h)).json()
    assert p["studied_count"] == 1
    assert p["total_lessons"] == 47
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
async def test_progresso_global_traz_as_quarenta_e_sete_aulas_sem_atividade(
    client: AsyncClient,
) -> None:
    h = await conta(client, "zerado")
    p = (await client.get("/api/me/progress", headers=h)).json()
    assert len(p["lessons"]) == 47
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
            f"/api/exercises/{ex['id']}/attempt", json=tentativa("faster"), headers=ana
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


@pytest.mark.asyncio
async def test_tentativa_repetida_com_a_mesma_chave_nao_duplica(client: AsyncClient) -> None:
    headers = await conta(client, "idempotente")
    ex = await primeiro_exercicio(client)
    body = tentativa("more fast", 77)

    first = await client.post(f"/api/exercises/{ex['id']}/attempt", json=body, headers=headers)
    repeated = await client.post(f"/api/exercises/{ex['id']}/attempt", json=body, headers=headers)
    conflict = await client.post(
        f"/api/exercises/{ex['id']}/attempt",
        json={**body, "answer": "faster"},
        headers=headers,
    )
    progress = (await client.get("/api/me/progress", headers=headers)).json()

    assert first.status_code == repeated.status_code == 200
    assert first.json()["attempt_id"] == repeated.json()["attempt_id"]
    assert progress["attempts"] == 1
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_dicas_sao_liberadas_progressivamente(client: AsyncClient) -> None:
    headers = await conta(client, "dicas")
    ex = await primeiro_exercicio(client)
    base = f"/api/exercises/{ex['id']}/hints"

    first = await client.get(f"{base}/1", headers=headers)
    blocked = await client.get(f"{base}/2", headers=headers)
    await client.post(
        f"/api/exercises/{ex['id']}/attempt",
        json=tentativa("more fast", 88),
        headers=headers,
    )
    second = await client.get(f"{base}/2", headers=headers)

    assert first.status_code == 200
    assert first.json()["level"] == 1
    assert blocked.status_code == 409
    assert second.status_code == 200
    assert second.json()["level"] == 2
    assert "faster" not in (first.text + second.text).lower()
