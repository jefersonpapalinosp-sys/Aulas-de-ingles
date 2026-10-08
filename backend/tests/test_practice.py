"""Sessões retomáveis e contrato protegido do laboratório de exercícios."""

import asyncio
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Exercise, ExerciseHint, Lesson, PracticeSession


async def conta(client: AsyncClient, sufixo: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"practice-{sufixo}@exemplo.com",
            "password": "senha-bem-grande",
            "display_name": sufixo,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_body(**overrides: object) -> dict[str, object]:
    return {
        "idempotency_key": str(uuid4()),
        "mode": "guided",
        **overrides,
    }


def attempt(answer: str, practice_session_id: int) -> dict[str, object]:
    return {
        "answer": answer,
        "idempotency_key": str(uuid4()),
        "practice_session_id": practice_session_id,
    }


@pytest.mark.asyncio
async def test_lista_canonica_filtra_sem_vazar_feedback(client: AsyncClient) -> None:
    response = await client.get("/api/courses/voa-level-1/lessons/31/exercises?objective=correct")

    assert response.status_code == 200
    exercises = response.json()
    assert len(exercises) == 2
    assert {exercise["objective"] for exercise in exercises} == {"correct"}
    assert all(exercise["hint"] is None for exercise in exercises)
    assert all(exercise["explanation"] is None for exercise in exercises)
    assert "answers" not in response.text
    assert (
        await client.get("/api/courses/voa-level-1/lessons/31/exercises?objective=invalid")
    ).status_code == 422
    assert (
        await client.get("/api/courses/curso-inexistente/lessons/31/exercises")
    ).status_code == 404


@pytest.mark.asyncio
async def test_openapi_documenta_retomada_com_status_200(client: AsyncClient) -> None:
    contract = (await client.get("/openapi.json")).json()
    operation = contract["paths"]["/api/courses/{course_slug}/lessons/{number}/practice-sessions"][
        "post"
    ]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PracticeSessionOut"
    }
    assert "201" in operation["responses"]


@pytest.mark.asyncio
async def test_criacao_retomada_e_posicao_sao_idempotentes(client: AsyncClient) -> None:
    headers = await conta(client, "resume")
    url = "/api/courses/voa-level-1/lessons/31/practice-sessions"
    body = create_body(mode="quick")

    empty = await client.get(f"{url}/active", headers=headers)
    created = await client.post(url, headers=headers, json=body)
    replay = await client.post(url, headers=headers, json=body)
    resumed_with_new_key = await client.post(url, headers=headers, json=create_body(mode="quick"))
    active = await client.get(f"{url}/active", headers=headers)

    assert empty.status_code == 204
    assert empty.headers["cache-control"] == "private, no-store"
    assert created.status_code == 201
    assert replay.status_code == 200
    assert resumed_with_new_key.status_code == 200
    data = created.json()
    assert (
        replay.json()["id"]
        == resumed_with_new_key.json()["id"]
        == active.json()["id"]
        == data["id"]
    )
    assert data["summary"] == {
        "total": 5,
        "completed": 0,
        "first_try_correct": 0,
        "corrected": 0,
        "revealed": 0,
        "pending": 5,
    }
    assert data["content_version"] == 2
    assert data["content_changed"] is False
    assert active.headers["cache-control"] == "private, no-store"

    position_key = str(uuid4())
    moved = await client.put(
        f"/api/practice-sessions/{data['id']}/position",
        headers=headers,
        json={
            "current_position": 2,
            "expected_revision": 1,
            "idempotency_key": position_key,
        },
    )
    repeated = await client.put(
        f"/api/practice-sessions/{data['id']}/position",
        headers=headers,
        json={
            "current_position": 2,
            "expected_revision": 1,
            "idempotency_key": position_key,
        },
    )
    assert moved.json()["state_revision"] == repeated.json()["state_revision"] == 2
    assert repeated.json()["current_position"] == 2

    reused_with_other_payload = await client.put(
        f"/api/practice-sessions/{data['id']}/position",
        headers=headers,
        json={
            "current_position": 3,
            "expected_revision": 1,
            "idempotency_key": position_key,
        },
    )
    assert reused_with_other_payload.status_code == 409
    assert (
        reused_with_other_payload.json()["detail"]["code"]
        == "practice_position_idempotency_mismatch"
    )

    conflict = await client.put(
        f"/api/practice-sessions/{data['id']}/position",
        headers=headers,
        json={
            "current_position": 3,
            "expected_revision": 1,
            "idempotency_key": str(uuid4()),
        },
    )
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_posicao_concorrente_aplica_compare_and_swap(client: AsyncClient) -> None:
    headers = await conta(client, "position-cas")
    practice = (
        await client.post(
            "/api/courses/voa-level-1/lessons/31/practice-sessions",
            headers=headers,
            json=create_body(mode="quick"),
        )
    ).json()
    url = f"/api/practice-sessions/{practice['id']}/position"

    first, second = await asyncio.gather(
        client.put(
            url,
            headers=headers,
            json={
                "current_position": 1,
                "expected_revision": 1,
                "idempotency_key": str(uuid4()),
            },
        ),
        client.put(
            url,
            headers=headers,
            json={
                "current_position": 2,
                "expected_revision": 1,
                "idempotency_key": str(uuid4()),
            },
        ),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    winner = first if first.status_code == 200 else second
    loser = second if first.status_code == 200 else first
    assert winner.json()["state_revision"] == 2
    assert loser.json()["detail"]["code"] == "practice_revision_conflict"
    resumed = await client.get(f"/api/practice-sessions/{practice['id']}", headers=headers)
    assert resumed.json()["state_revision"] == 2
    assert resumed.json()["current_position"] == winner.json()["current_position"]


@pytest.mark.asyncio
async def test_tentativa_dicas_reveal_e_resumo_da_sessao(client: AsyncClient) -> None:
    headers = await conta(client, "feedback")
    created = (
        await client.post(
            "/api/courses/voa-level-1/lessons/31/practice-sessions",
            headers=headers,
            json=create_body(),
        )
    ).json()
    session_id = created["id"]
    first_id = created["items"][0]["exercise"]["id"]
    second_id = created["items"][1]["exercise"]["id"]

    blocked = await client.post(
        f"/api/practice-sessions/{session_id}/items/{first_id}/hints/2",
        headers=headers,
    )
    wrong_body = attempt("more fast", session_id)
    wrong = await client.post(
        f"/api/exercises/{first_id}/attempt", headers=headers, json=wrong_body
    )
    replay = await client.post(
        f"/api/exercises/{first_id}/attempt", headers=headers, json=wrong_body
    )
    first_hint = await client.post(
        f"/api/practice-sessions/{session_id}/items/{first_id}/hints/1",
        headers=headers,
    )
    second_hint = await client.post(
        f"/api/practice-sessions/{session_id}/items/{first_id}/hints/2",
        headers=headers,
    )
    correct = await client.post(
        f"/api/exercises/{first_id}/attempt",
        headers=headers,
        json=attempt("faster", session_id),
    )
    revealed = await client.post(
        f"/api/practice-sessions/{session_id}/items/{second_id}/reveal",
        headers=headers,
    )

    assert blocked.status_code == 409
    assert wrong.status_code == replay.status_code == 200
    assert wrong.headers["cache-control"] == "private, no-store"
    assert wrong.json()["attempt_id"] == replay.json()["attempt_id"]
    assert wrong.json()["session"]["attempt_count"] == 1
    assert first_hint.status_code == 200
    assert second_hint.status_code == 200
    assert second_hint.headers["cache-control"] == "private, no-store"
    assert second_hint.json()["item"]["highest_hint_level"] == 2
    assert correct.json()["session"]["first_try_correct"] is False
    assert correct.json()["session"]["outcome"] == "corrected"
    assert revealed.json()["answers"] == ["more comfortable"]
    assert revealed.headers["cache-control"] == "private, no-store"
    assert revealed.json()["item"]["outcome"] == "revealed"

    resumed = (await client.get(f"/api/practice-sessions/{session_id}", headers=headers)).json()
    assert resumed["summary"]["corrected"] == 1
    assert resumed["summary"]["revealed"] == 1
    assert resumed["summary"]["pending"] == 8
    assert resumed["items"][0]["first_try_correct"] is False
    assert len(resumed["items"][0]["opened_hints"]) == 2
    assert resumed["items"][1]["answers"] == ["more comfortable"]


@pytest.mark.asyncio
async def test_sincronizacao_concorrente_da_mesma_tentativa_nao_duplica(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "concurrent")
    practice = (
        await client.post(
            "/api/courses/voa-level-1/lessons/31/practice-sessions",
            headers=headers,
            json=create_body(mode="quick"),
        )
    ).json()
    exercise_id = practice["items"][0]["exercise"]["id"]
    body = attempt("more fast", practice["id"])

    first, second = await asyncio.gather(
        client.post(f"/api/exercises/{exercise_id}/attempt", headers=headers, json=body),
        client.post(f"/api/exercises/{exercise_id}/attempt", headers=headers, json=body),
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["attempt_id"] == second.json()["attempt_id"]
    assert first.json()["session"]["attempt_count"] == 1
    assert second.json()["session"]["attempt_count"] == 1


@pytest.mark.asyncio
async def test_tentativas_concorrentes_preservam_contador_e_primeiro_resultado(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "concurrent-distinct")
    practice = (
        await client.post(
            "/api/courses/voa-level-1/lessons/31/practice-sessions",
            headers=headers,
            json=create_body(mode="quick"),
        )
    ).json()
    exercise_id = practice["items"][0]["exercise"]["id"]

    first, second = await asyncio.gather(
        client.post(
            f"/api/exercises/{exercise_id}/attempt",
            headers=headers,
            json=attempt("more fast", practice["id"]),
        ),
        client.post(
            f"/api/exercises/{exercise_id}/attempt",
            headers=headers,
            json=attempt("fastest", practice["id"]),
        ),
    )

    assert first.status_code == second.status_code == 200
    assert sorted(
        [first.json()["session"]["attempt_count"], second.json()["session"]["attempt_count"]]
    ) == [1, 2]
    resumed = (await client.get(f"/api/practice-sessions/{practice['id']}", headers=headers)).json()
    assert resumed["items"][0]["attempt_count"] == 2
    assert resumed["items"][0]["first_try_correct"] is False


@pytest.mark.asyncio
async def test_ultimas_tentativas_concorrentes_concluem_a_sessao(client: AsyncClient) -> None:
    headers = await conta(client, "concurrent-completion")
    practice = (
        await client.post(
            "/api/courses/voa-level-1/lessons/31/practice-sessions",
            headers=headers,
            json=create_body(mode="quick"),
        )
    ).json()
    answers = ["faster", "more comfortable", "bigger than", "better", "much"]

    for item, answer in zip(practice["items"][:3], answers[:3], strict=True):
        response = await client.post(
            f"/api/exercises/{item['exercise']['id']}/attempt",
            headers=headers,
            json=attempt(answer, practice["id"]),
        )
        assert response.status_code == 200

    first, second = await asyncio.gather(
        client.post(
            f"/api/exercises/{practice['items'][3]['exercise']['id']}/attempt",
            headers=headers,
            json=attempt(answers[3], practice["id"]),
        ),
        client.post(
            f"/api/exercises/{practice['items'][4]['exercise']['id']}/attempt",
            headers=headers,
            json=attempt(answers[4], practice["id"]),
        ),
    )

    assert first.status_code == second.status_code == 200
    assert {
        first.json()["session"]["session_status"],
        second.json()["session"]["session_status"],
    } == {
        "active",
        "completed",
    }
    resumed = (await client.get(f"/api/practice-sessions/{practice['id']}", headers=headers)).json()
    assert resumed["status"] == "completed"
    assert resumed["summary"]["completed"] == resumed["summary"]["total"] == 5


@pytest.mark.asyncio
async def test_repetir_erros_materializa_apenas_itens_frageis(client: AsyncClient) -> None:
    headers = await conta(client, "mistakes")
    base = "/api/courses/voa-level-1/lessons/31/practice-sessions"
    source = (
        await client.post(
            base,
            headers=headers,
            json=create_body(objective="correct"),
        )
    ).json()
    first, second = source["items"]
    first_id = first["exercise"]["id"]
    second_id = second["exercise"]["id"]

    await client.post(
        f"/api/exercises/{first_id}/attempt",
        headers=headers,
        json=attempt("more faster", source["id"]),
    )
    await client.post(
        f"/api/exercises/{first_id}/attempt",
        headers=headers,
        json=attempt("faster", source["id"]),
    )
    finished = await client.post(
        f"/api/exercises/{second_id}/attempt",
        headers=headers,
        json=attempt("bigger than", source["id"]),
    )
    assert finished.json()["session"]["session_status"] == "completed"

    retry = await client.post(
        base,
        headers=headers,
        json=create_body(mode="mistakes", objective="correct", source_session_id=source["id"]),
    )
    assert retry.status_code == 201
    assert retry.json()["summary"]["total"] == 1
    assert retry.json()["items"][0]["exercise"]["id"] == first_id


@pytest.mark.asyncio
async def test_excluir_sessao_fonte_remove_sessao_mistakes_por_cascade(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "source-cascade")
    base = "/api/courses/voa-level-1/lessons/31/practice-sessions"
    source = (await client.post(base, headers=headers, json=create_body(mode="quick"))).json()

    source_model = (
        await session.execute(select(PracticeSession).where(PracticeSession.id == source["id"]))
    ).scalar_one()
    source_model.status = "completed"
    source_model.items[0].first_try_correct = False
    await session.commit()

    retry = await client.post(
        base,
        headers=headers,
        json=create_body(mode="mistakes", source_session_id=source["id"]),
    )
    assert retry.status_code == 201
    retry_id = retry.json()["id"]

    await session.execute(delete(PracticeSession).where(PracticeSession.id == source["id"]))
    await session.commit()

    remaining = (
        await session.execute(
            select(PracticeSession.id).where(PracticeSession.id.in_([source["id"], retry_id]))
        )
    ).scalars()
    assert list(remaining) == []


@pytest.mark.asyncio
async def test_origem_so_e_aceita_em_mistakes_concluida_e_da_mesma_conta(
    client: AsyncClient, session: AsyncSession
) -> None:
    ana = await conta(client, "source-ana")
    bia = await conta(client, "source-bia")
    base = "/api/courses/voa-level-1/lessons/31/practice-sessions"
    source = (await client.post(base, headers=ana, json=create_body(mode="quick"))).json()

    cross_tenant_quick = await client.post(
        base,
        headers=bia,
        json=create_body(mode="quick", source_session_id=source["id"]),
    )
    assert cross_tenant_quick.status_code == 422
    assert (await client.get(f"{base}/active", headers=bia)).status_code == 204

    source_model = (
        await session.execute(select(PracticeSession).where(PracticeSession.id == source["id"]))
    ).scalar_one()
    source_model.status = "abandoned"
    await session.commit()

    abandoned = await client.post(
        base,
        headers=ana,
        json=create_body(mode="mistakes", source_session_id=source["id"]),
    )
    assert abandoned.status_code == 409
    assert abandoned.json()["detail"] == {
        "code": "practice_source_not_completed",
        "status": "abandoned",
    }


@pytest.mark.asyncio
async def test_sessao_e_isolada_por_conta(client: AsyncClient) -> None:
    ana = await conta(client, "ana")
    bia = await conta(client, "bia")
    practice = (
        await client.post(
            "/api/courses/voa-level-1/lessons/31/practice-sessions",
            headers=ana,
            json=create_body(mode="quick"),
        )
    ).json()

    assert (
        await client.get(f"/api/practice-sessions/{practice['id']}", headers=bia)
    ).status_code == 404
    exercise_id = practice["items"][0]["exercise"]["id"]
    assert (
        await client.post(
            f"/api/exercises/{exercise_id}/attempt",
            headers=bia,
            json=attempt("faster", practice["id"]),
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_mudanca_de_conteudo_bloqueia_correcao_e_permite_recomecar(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "version")
    base = "/api/courses/voa-level-1/lessons/31/practice-sessions"
    practice = (await client.post(base, headers=headers, json=create_body(mode="quick"))).json()
    exercise_id = practice["items"][0]["exercise"]["id"]
    accepted_body = attempt("faster", practice["id"])
    accepted = await client.post(
        f"/api/exercises/{exercise_id}/attempt",
        headers=headers,
        json=accepted_body,
    )
    assert accepted.status_code == 200

    lesson = (await session.execute(select(Lesson).where(Lesson.number == 31))).scalar_one()
    exercise = (
        await session.execute(
            select(Exercise).where(
                Exercise.lesson_id == lesson.id,
                Exercise.id == exercise_id,
            )
        )
    ).scalar_one()
    original = exercise.prompt
    original_explanation = exercise.explanation
    try:
        exercise.prompt = f"{original} (revisado)"
        exercise.explanation = "EXPLICAÇÃO NOVA QUE NÃO PODE VAZAR NO REPLAY"
        await session.commit()

        stale = await client.get(f"/api/practice-sessions/{practice['id']}", headers=headers)
        blocked = await client.post(
            f"/api/exercises/{exercise_id}/attempt",
            headers=headers,
            json=attempt("faster", practice["id"]),
        )
        replayed = await client.post(
            f"/api/exercises/{exercise_id}/attempt",
            headers=headers,
            json=accepted_body,
        )
        restarted = await client.post(base, headers=headers, json=create_body(mode="quick"))

        assert stale.json()["content_changed"] is True
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "practice_content_changed"
        assert replayed.status_code == 409
        assert replayed.json()["detail"]["code"] == "practice_content_changed"
        assert "EXPLICAÇÃO NOVA" not in replayed.text
        assert restarted.status_code == 201
        assert restarted.json()["id"] != practice["id"]
        assert restarted.json()["content_changed"] is False
    finally:
        exercise.prompt = original
        exercise.explanation = original_explanation
        await session.commit()


@pytest.mark.asyncio
async def test_mudanca_apenas_do_nivel_da_dica_invalida_fingerprint(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "hint-fingerprint")
    practice = (
        await client.post(
            "/api/courses/voa-level-1/lessons/31/practice-sessions",
            headers=headers,
            json=create_body(mode="quick"),
        )
    ).json()
    exercise_id = practice["items"][0]["exercise"]["id"]
    hint = (
        await session.execute(
            select(ExerciseHint).where(
                ExerciseHint.exercise_id == exercise_id,
                ExerciseHint.level == 2,
            )
        )
    ).scalar_one()

    try:
        hint.level = 3
        await session.commit()
        stale = await client.get(f"/api/practice-sessions/{practice['id']}", headers=headers)
        assert stale.status_code == 200
        assert stale.json()["content_changed"] is True
    finally:
        hint.level = 2
        await session.commit()
