"""Rascunho, versões, feedback e isolamento da produção escrita."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app
from app.services import assistance


async def conta(client: AsyncClient, sufixo: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"escrita-{sufixo}@exemplo.com",
            "password": "senha-bem-grande",
            "display_name": sufixo,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def proposta(client: AsyncClient) -> dict[str, object]:
    return (await client.get("/api/lessons/31")).json()["writing_prompts"][0]


@pytest.mark.asyncio
async def test_workspace_exige_login(client: AsyncClient) -> None:
    prompt = await proposta(client)
    base = f"/api/writing/prompts/{prompt['id']}"

    assert (await client.get(f"{base}/draft")).status_code == 401
    assert (await client.put(f"{base}/draft", json={"text": "Hi."})).status_code == 401
    assert (await client.post(f"{base}/versions", json={"text": "Hi."})).status_code == 401
    assert (await client.post(f"{base}/feedback", json={"text": "Hi."})).status_code == 401


@pytest.mark.asyncio
async def test_rascunho_e_versoes_sobrevivem_a_nova_sessao(client: AsyncClient) -> None:
    headers = await conta(client, "persistencia")
    prompt = await proposta(client)
    base = f"/api/writing/prompts/{prompt['id']}"
    inicial = (await client.get(f"{base}/draft", headers=headers)).json()
    assert inicial == {
        "prompt_id": prompt["id"],
        "text": "",
        "updated_at": None,
        "revisions": [],
    }

    first_text = "The Metro is faster than the bus. Visitors should take it."
    salvo = await client.put(f"{base}/draft", headers=headers, json={"text": first_text})
    assert salvo.status_code == 200
    assert salvo.json()["text"] == first_text
    assert salvo.json()["updated_at"] is not None

    first_version = await client.post(
        f"{base}/versions", headers=headers, json={"text": first_text}
    )
    repeated_version = await client.post(
        f"{base}/versions", headers=headers, json={"text": first_text}
    )
    second_text = f"{first_text} It is also more comfortable."
    second_version = await client.post(
        f"{base}/versions", headers=headers, json={"text": second_text}
    )
    assert first_version.json()["version"] == 1
    assert repeated_version.json()["id"] == first_version.json()["id"]
    assert second_version.json()["version"] == 2

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as outro_navegador:
        login = await outro_navegador.post(
            "/api/auth/login",
            json={
                "email": "escrita-persistencia@exemplo.com",
                "password": "senha-bem-grande",
            },
        )
        second_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        retomado = (await outro_navegador.get(f"{base}/draft", headers=second_headers)).json()

    assert retomado["text"] == second_text
    assert [item["version"] for item in retomado["revisions"]] == [2, 1]


@pytest.mark.asyncio
async def test_rascunho_e_isolado_por_conta(client: AsyncClient) -> None:
    prompt = await proposta(client)
    base = f"/api/writing/prompts/{prompt['id']}"
    ana = await conta(client, "ana")
    await client.put(f"{base}/draft", headers=ana, json={"text": "Ana's private draft."})

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as outro:
        bruno = await conta(outro, "bruno")
        draft = (await outro.get(f"{base}/draft", headers=bruno)).json()

    assert draft["text"] == ""
    assert draft["revisions"] == []


@pytest.mark.asyncio
async def test_feedback_aponta_pendencias_e_aprova_texto_pronto(client: AsyncClient) -> None:
    headers = await conta(client, "feedback")
    prompt = await proposta(client)
    url = f"/api/writing/prompts/{prompt['id']}/feedback"

    incompleto = (await client.post(url, headers=headers, json={"text": "bus is fast"})).json()
    assert incompleto["ready"] is False
    assert incompleto["word_count"] == 3
    assert any(not check["passed"] for check in incompleto["checks"])
    writing_review = (
        await client.get("/api/review/due?item_type=writing_prompt", headers=headers)
    ).json()
    assert len(writing_review) == 1
    assert writing_review[0]["skill"] == "writing"

    pronto = (
        await client.post(
            url,
            headers=headers,
            json={
                "text": (
                    "The train is faster than the bus in my city. "
                    "It is comfortable and usually arrives on time. "
                    "A visitor should take the train to the stadium. "
                    "The bus is cheaper, but the train is my best choice."
                )
            },
        )
    ).json()
    assert pronto["ready"] is True
    assert pronto["word_count"] >= 35
    assert pronto["sentence_count"] == 4
    # Um novo feedback atualiza a origem, mas nunca duplica a revisão.
    assert len((await client.get("/api/review/items?status=active", headers=headers)).json()) == 1


@pytest.mark.asyncio
async def test_proposta_inexistente_e_texto_vazio_sao_validados(client: AsyncClient) -> None:
    headers = await conta(client, "validacao")

    inexistente = await client.get("/api/writing/prompts/999999/draft", headers=headers)
    assert inexistente.status_code == 404
    vazio = await client.post(
        "/api/writing/prompts/999999/versions", headers=headers, json={"text": "  "}
    )
    assert vazio.status_code == 422


@pytest.mark.asyncio
async def test_feedback_assistido_e_opcional_avaliavel_e_tem_fallback(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_writing_url", "http://provider.test/writing")
    monkeypatch.setattr(settings, "assist_provider_name", "provider-test")
    monkeypatch.setattr(settings, "assist_daily_quota", 2)
    monkeypatch.setattr(
        assistance,
        "call_writing_provider",
        lambda *args, **kwargs: assistance.WritingAssistResult(
            summary="A ideia está clara; revise a escolha de transporte.",
            suggestions=[{"criterion": "clarity", "message": "Explique por que é mais rápido."}],
            confidence=0.71,
            cost_microusd=2300,
        ),
    )
    headers = await conta(client, "assistido")
    prompt = await proposta(client)
    response = await client.post(
        f"/api/writing/prompts/{prompt['id']}/feedback",
        headers=headers,
        json={"text": "The bus is faster.", "assisted": True},
    )
    assert response.status_code == 200
    feedback = response.json()
    assert feedback["analysis_mode"] == "assisted"
    assert feedback["automated"] is True
    assert feedback["evaluation_only"] is True
    assert feedback["low_confidence"] is True
    assert feedback["assisted_summary"].startswith("A ideia")
    assert feedback["assisted_cost_microusd"] == 2300

    rated = await client.put(
        f"/api/writing/feedback/{feedback['id']}/rating",
        headers=headers,
        json={"rating": "helpful"},
    )
    assert rated.json()["human_rating"] == "helpful"

    def fail(*args: object, **kwargs: object) -> assistance.WritingAssistResult:
        raise assistance.ProviderFailure("provider_unavailable")

    monkeypatch.setattr(assistance, "call_writing_provider", fail)
    fallback = (
        await client.post(
            f"/api/writing/prompts/{prompt['id']}/feedback",
            headers=headers,
            json={"text": "My draft remains safe.", "assisted": True},
        )
    ).json()
    assert fallback["analysis_mode"] == "fallback"
    assert fallback["assisted_error_code"] == "provider_unavailable"
    assert fallback["checks"]

    quota = (
        await client.post(
            f"/api/writing/prompts/{prompt['id']}/feedback",
            headers=headers,
            json={"text": "This draft also remains safe.", "assisted": True},
        )
    ).json()
    assert quota["analysis_mode"] == "fallback"
    assert quota["assisted_error_code"] == "quota_exceeded"
