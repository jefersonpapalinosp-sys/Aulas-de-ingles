"""Caderno pessoal, isolamento e exportação dos dados do aluno."""

import pytest
from httpx import AsyncClient


async def conta(client: AsyncClient, sufixo: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"caderno-{sufixo}@exemplo.com",
            "password": "senha-bem-grande",
            "display_name": sufixo,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_caderno_exige_login_e_valida_conteudo(client: AsyncClient) -> None:
    body = {"lesson_number": 31, "kind": "note", "content": "Remember faster than."}
    assert (await client.get("/api/me/notebook")).status_code == 401
    assert (await client.post("/api/me/notebook", json=body)).status_code == 401
    assert (await client.get("/api/me/export")).status_code == 401

    headers = await conta(client, "validacao")
    blank = await client.post("/api/me/notebook", headers=headers, json={**body, "content": "   "})
    invalid_kind = await client.post(
        "/api/me/notebook", headers=headers, json={**body, "kind": "public"}
    )
    missing_lesson = await client.post(
        "/api/me/notebook", headers=headers, json={**body, "lesson_number": 9999}
    )
    assert blank.status_code == 422
    assert invalid_kind.status_code == 422
    assert missing_lesson.status_code == 404


@pytest.mark.asyncio
async def test_crud_filtros_e_isolamento_do_caderno(client: AsyncClient) -> None:
    ana = await conta(client, "ana")
    created = await client.post(
        "/api/me/notebook",
        headers=ana,
        json={
            "lesson_number": 31,
            "kind": "favorite_phrase",
            "content": "A taxi is faster than a bus.",
        },
    )
    assert created.status_code == 201
    entry = created.json()
    assert entry["lesson_number"] == 31
    assert entry["lesson_title"] == "Take Me Out to the Ball Game"
    review = (await client.get("/api/review/due?item_type=phrase", headers=ana)).json()
    assert [item["answer"] for item in review] == ["A taxi is faster than a bus."]

    await client.post(
        "/api/me/notebook",
        headers=ana,
        json={"lesson_number": 32, "kind": "note", "content": "Objects after verbs."},
    )
    filtered = (
        await client.get("/api/me/notebook?lesson=31&kind=favorite_phrase", headers=ana)
    ).json()
    assert [item["id"] for item in filtered] == [entry["id"]]

    updated = await client.put(
        f"/api/me/notebook/{entry['id']}",
        headers=ana,
        json={"kind": "personal_example", "content": "The subway is faster than my car."},
    )
    assert updated.status_code == 200
    assert updated.json()["kind"] == "personal_example"
    assert (await client.get("/api/review/due?item_type=phrase", headers=ana)).json() == []

    bruno = await conta(client, "bruno")
    assert (await client.get("/api/me/notebook", headers=bruno)).json() == []
    assert (
        await client.put(
            f"/api/me/notebook/{entry['id']}",
            headers=bruno,
            json={"kind": "note", "content": "Tentativa de alteração"},
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/me/notebook/{entry['id']}", headers=bruno)
    ).status_code == 404

    assert (await client.delete(f"/api/me/notebook/{entry['id']}", headers=ana)).status_code == 204
    remaining = (await client.get("/api/me/notebook", headers=ana)).json()
    assert len(remaining) == 1


@pytest.mark.asyncio
async def test_exportacao_reune_dados_sem_segredos(client: AsyncClient) -> None:
    headers = await conta(client, "exportacao")
    lesson = (await client.get("/api/lessons/31")).json()
    prompt = lesson["writing_prompts"][0]
    text = "The train is faster than the bus. Visitors should take the train."

    await client.put("/api/lessons/31/studied", headers=headers)
    await client.put(
        f"/api/media/{lesson['media'][0]['id']}/position",
        headers=headers,
        json={"position_seconds": 42.5},
    )
    await client.put(
        f"/api/writing/prompts/{prompt['id']}/draft", headers=headers, json={"text": text}
    )
    await client.post(
        f"/api/writing/prompts/{prompt['id']}/versions", headers=headers, json={"text": text}
    )
    feedback = await client.post(
        f"/api/writing/prompts/{prompt['id']}/feedback", headers=headers, json={"text": text}
    )
    assert feedback.status_code == 200
    assert feedback.json()["id"] > 0
    assert feedback.json()["created_at"] is not None
    await client.post(
        "/api/me/notebook",
        headers=headers,
        json={"lesson_number": 31, "kind": "note", "content": "Review comparatives."},
    )

    exported = await client.get("/api/me/export", headers=headers)
    assert exported.status_code == 200
    assert exported.headers["content-disposition"] == (
        'attachment; filename="aulas-ingles-dados.json"'
    )
    data = exported.json()
    assert data["schema_version"] == "1.4"
    assert data["profile"]["email"] == "caderno-exportacao@exemplo.com"
    assert data["lesson_progress"][0]["lesson_number"] == 31
    assert data["media_progress"][0]["position_seconds"] == 42.5
    assert data["writing"][0]["draft"] == text
    assert data["writing"][0]["revisions"][0]["version"] == 1
    assert data["writing"][0]["feedbacks"][0]["text"] == text
    assert data["notebook"][0]["content"] == "Review comparatives."
    assert data["review_items"][0]["item_type"] == "vocabulary"

    serialized = exported.text.lower()
    for secret in ("password", "password_hash", "access_token", "refresh_token", "storage_key"):
        assert secret not in serialized


@pytest.mark.asyncio
async def test_historico_de_escrita_e_privado(client: AsyncClient) -> None:
    lesson = (await client.get("/api/lessons/31")).json()
    prompt = lesson["writing_prompts"][0]
    ana = await conta(client, "historico-ana")
    text = "The Metro is faster than the bus. You should take it."
    await client.post(
        f"/api/writing/prompts/{prompt['id']}/versions", headers=ana, json={"text": text}
    )
    await client.post(
        f"/api/writing/prompts/{prompt['id']}/feedback", headers=ana, json={"text": text}
    )

    history = (await client.get("/api/writing/history", headers=ana)).json()
    assert len(history) == 1
    assert history[0]["lesson_number"] == 31
    assert history[0]["revisions"][0]["text"] == text
    assert history[0]["feedbacks"][0]["id"] > 0

    bruno = await conta(client, "historico-bruno")
    assert (await client.get("/api/writing/history", headers=bruno)).json() == []
