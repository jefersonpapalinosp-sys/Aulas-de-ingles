"""Checkpoint curricular por unidade, com correção e histórico privados."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CourseReview, CourseReviewAttempt, CourseUnit

REVIEW_URL = "/api/courses/voa-level-1/units/40-44/review"
LEVEL_2_REVIEW_URL = "/api/courses/voa-level-2/units/6-10/review"


async def conta(client: AsyncClient, sufixo: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"checkpoint-{sufixo}@exemplo.com",
            "password": "senha-bem-grande",
            "display_name": sufixo,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def respostas_corretas(detail: dict[str, object]) -> list[dict[str, object]]:
    questions = detail["questions"]
    assert isinstance(questions, list)
    answers_by_position = {
        1: "uma árvore",
        2: "will see",
        3: "Anna hurt herself.",
        4: "Would you be able to help me?",
        5: "You don't have to buy bread.",
        6: "will succeed · yourself · must",
    }
    return [
        {
            "question_id": question["id"],
            "answer": answers_by_position[question["position"]],
        }
        for question in questions
    ]


def attempt_body(
    detail: dict[str, object],
    *,
    key: str | None = None,
    correct: bool = True,
    content_version: int | None = None,
) -> dict[str, object]:
    questions = detail["questions"]
    assert isinstance(questions, list)
    answers = (
        respostas_corretas(detail)
        if correct
        else [
            {"question_id": question["id"], "answer": "resposta incorreta"}
            for question in questions
        ]
    )
    return {
        "idempotency_key": key or str(uuid4()),
        "content_version": content_version or int(detail["content_version"]),
        "answers": answers,
    }


@pytest.mark.asyncio
async def test_checkpoint_exige_login_e_rotas_inexistentes_retornam_404(
    client: AsyncClient,
) -> None:
    assert (await client.get(REVIEW_URL)).status_code == 401
    assert (await client.post(f"{REVIEW_URL}/attempts", json={})).status_code == 401

    headers = await conta(client, "not-found")
    assert (
        await client.get("/api/courses/curso-inexistente/units/40-44/review", headers=headers)
    ).status_code == 404
    assert (
        await client.get(
            "/api/courses/voa-level-1/units/unidade-inexistente/review",
            headers=headers,
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_detalhe_do_checkpoint_e_seguro_e_retoma_listening_da_aula_40(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "detail")
    response = await client.get(REVIEW_URL, headers=headers)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert "accepted_answers" not in response.text
    detail = response.json()
    assert detail["slug"] == "checkpoint-40-44"
    assert detail["content_version"] == 1
    assert detail["latest_attempt"] is None
    assert len(detail["questions"]) == 6
    assert [question["position"] for question in detail["questions"]] == list(range(1, 7))
    assert all("accepted_answers" not in question for question in detail["questions"])
    lesson_40 = (await client.get("/api/courses/voa-level-1/lessons/40")).json()
    assert detail["listening_media"] == lesson_40["media"][0]
    assert detail["listening_source_page_url"] == lesson_40["voa_url"]


@pytest.mark.asyncio
async def test_checkpoint_6_10_do_level_2_usa_aula_9_e_isola_historico(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "level-2-6-10")
    response = await client.get(LEVEL_2_REVIEW_URL, headers=headers)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert "accepted_answers" not in response.text
    detail = response.json()
    assert detail["slug"] == "checkpoint-6-10"
    assert len(detail["questions"]) == 6
    assert [question["position"] for question in detail["questions"]] == list(range(1, 7))
    lesson_9 = (await client.get("/api/courses/voa-level-2/lessons/9")).json()
    assert detail["listening_media"] == lesson_9["media"][0]
    assert detail["listening_source_page_url"] == lesson_9["voa_url"]

    failed = await client.post(
        f"{LEVEL_2_REVIEW_URL}/attempts",
        headers=headers,
        json=attempt_body(detail, correct=False),
    )
    assert failed.status_code == 201, failed.text
    assert failed.json()["reinforced_lesson_numbers"] == [6, 7, 8, 9, 10]
    assert (await client.get(LEVEL_2_REVIEW_URL, headers=headers)).json()["latest_attempt"][
        "id"
    ] == failed.json()["id"]
    first_checkpoint = await client.get(
        "/api/courses/voa-level-2/units/1-5/review", headers=headers
    )
    assert first_checkpoint.status_code == 200
    assert first_checkpoint.json()["latest_attempt"] is None


@pytest.mark.asyncio
async def test_checkpoint_persiste_gradua_e_expoe_a_ultima_tentativa(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "grade")
    detail = (await client.get(REVIEW_URL, headers=headers)).json()
    response = await client.post(
        f"{REVIEW_URL}/attempts",
        headers=headers,
        json=attempt_body(detail),
    )

    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "private, no-store"
    result = response.json()
    assert result["score"] == result["total"] == 6
    assert result["status"] == "consolidated"
    assert result["reinforced_lesson_numbers"] == []
    assert len(result["feedback"]) == 6
    assert all(item["correct"] is True for item in result["feedback"])
    assert all(item["explanation"] for item in result["feedback"])

    stored = (
        await session.execute(
            select(CourseReviewAttempt).where(CourseReviewAttempt.id == result["id"])
        )
    ).scalar_one()
    assert stored.score == stored.total == 6
    assert stored.content_version == detail["content_version"]

    refreshed = await client.get(REVIEW_URL, headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["latest_attempt"] == result


@pytest.mark.asyncio
async def test_checkpoint_indica_as_aulas_que_precisam_de_reforco(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "reinforce")
    detail = (await client.get(REVIEW_URL, headers=headers)).json()
    response = await client.post(
        f"{REVIEW_URL}/attempts",
        headers=headers,
        json=attempt_body(detail, correct=False),
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["score"] == 0
    assert result["total"] == 6
    assert result["status"] == "reinforce"
    assert result["reinforced_lesson_numbers"] == [40, 41, 42, 43, 44]
    assert len(result["feedback"]) == 6
    assert all(item["correct"] is False for item in result["feedback"])


@pytest.mark.asyncio
async def test_tentativa_do_checkpoint_e_idempotente_e_rejeita_reuso_conflitante(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "idempotent")
    detail = (await client.get(REVIEW_URL, headers=headers)).json()
    key = str(uuid4())
    body = attempt_body(detail, key=key)

    created = await client.post(f"{REVIEW_URL}/attempts", headers=headers, json=body)
    replay = await client.post(f"{REVIEW_URL}/attempts", headers=headers, json=body)
    conflicting = await client.post(
        f"{REVIEW_URL}/attempts",
        headers=headers,
        json=attempt_body(detail, key=key, correct=False),
    )

    assert created.status_code == 201, created.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == created.json()
    assert conflicting.status_code == 409
    assert (
        await session.execute(select(func.count()).select_from(CourseReviewAttempt))
    ).scalar_one() == 1


@pytest.mark.asyncio
async def test_checkpoint_rejeita_versao_de_conteudo_obsoleta(client: AsyncClient) -> None:
    headers = await conta(client, "stale")
    detail = (await client.get(REVIEW_URL, headers=headers)).json()
    stale = await client.post(
        f"{REVIEW_URL}/attempts",
        headers=headers,
        json=attempt_body(detail, content_version=int(detail["content_version"]) + 1),
    )

    assert stale.status_code == 409
    assert "vers" in stale.text.lower()


@pytest.mark.asyncio
async def test_checkpoint_rejeita_conjunto_incompleto_ou_questao_alheia(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "invalid-set")
    detail = (await client.get(REVIEW_URL, headers=headers)).json()
    incomplete = attempt_body(detail)
    incomplete["answers"] = incomplete["answers"][:-1]
    alien = attempt_body(detail)
    alien["answers"][0]["question_id"] = 999_999

    assert (
        await client.post(f"{REVIEW_URL}/attempts", headers=headers, json=incomplete)
    ).status_code == 422
    assert (
        await client.post(f"{REVIEW_URL}/attempts", headers=headers, json=alien)
    ).status_code == 422


@pytest.mark.asyncio
async def test_nova_versao_nao_reutiliza_resultado_anterior(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "new-version")
    detail = (await client.get(REVIEW_URL, headers=headers)).json()
    created = await client.post(
        f"{REVIEW_URL}/attempts", headers=headers, json=attempt_body(detail)
    )
    assert created.status_code == 201

    review = (
        await session.execute(
            select(CourseReview)
            .join(CourseUnit, CourseReview.unit_id == CourseUnit.id)
            .where(CourseUnit.slug == "40-44")
        )
    ).scalar_one()
    original_version = review.content_version
    try:
        review.content_version = original_version + 1
        await session.commit()

        refreshed = await client.get(REVIEW_URL, headers=headers)
        assert refreshed.status_code == 200
        assert refreshed.json()["content_version"] == original_version + 1
        assert refreshed.json()["latest_attempt"] is None
    finally:
        review.content_version = original_version
        await session.commit()


@pytest.mark.asyncio
async def test_checkpoint_nao_publicado_nao_e_exposto(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "not-published")
    body = attempt_body((await client.get(REVIEW_URL, headers=headers)).json())
    review = (
        await session.execute(
            select(CourseReview)
            .join(CourseUnit, CourseReview.unit_id == CourseUnit.id)
            .where(CourseUnit.slug == "40-44")
        )
    ).scalar_one()
    original_status = review.status
    try:
        review.status = "planned"
        await session.commit()

        assert (await client.get(REVIEW_URL, headers=headers)).status_code == 404
        assert (
            await client.post(f"{REVIEW_URL}/attempts", headers=headers, json=body)
        ).status_code == 404
        curriculum = (await client.get("/api/courses/voa-level-1/curriculum")).json()
        unit = next(item for item in curriculum["units"] if item["slug"] == "40-44")
        assert unit["review"] is None
    finally:
        review.status = original_status
        await session.commit()


@pytest.mark.asyncio
async def test_historico_do_checkpoint_e_isolado_por_usuario(client: AsyncClient) -> None:
    ana = await conta(client, "ana")
    bruno = await conta(client, "bruno")
    detail_ana = (await client.get(REVIEW_URL, headers=ana)).json()
    shared_key = str(uuid4())

    attempt_ana = await client.post(
        f"{REVIEW_URL}/attempts",
        headers=ana,
        json=attempt_body(detail_ana, key=shared_key),
    )
    detail_bruno = (await client.get(REVIEW_URL, headers=bruno)).json()

    assert attempt_ana.status_code == 201
    assert detail_bruno["latest_attempt"] is None

    attempt_bruno = await client.post(
        f"{REVIEW_URL}/attempts",
        headers=bruno,
        json=attempt_body(detail_bruno, key=shared_key, correct=False),
    )
    assert attempt_bruno.status_code == 201
    assert attempt_bruno.json()["id"] != attempt_ana.json()["id"]
    assert (await client.get(REVIEW_URL, headers=ana)).json()["latest_attempt"][
        "id"
    ] == attempt_ana.json()["id"]
    assert (await client.get(REVIEW_URL, headers=bruno)).json()["latest_attempt"][
        "id"
    ] == attempt_bruno.json()["id"]
