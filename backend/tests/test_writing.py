"""Rascunho, versões, feedback e isolamento da produção escrita."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    User,
    WritingDraft,
    WritingFeedbackRecord,
    WritingPrompt,
    WritingRevision,
)
from app.main import create_app
from app.performance import BYTES_HEADER, POOL_HEADER, SQL_HEADER
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


# Helpers do contrato pós-cutover (LEGACY_WRITES_UNTIL): toda escrita de
# rascunho/versão envia `expected_revision`, como o cliente atual faz. Quando o
# chamador não propaga a revisão da resposta anterior, lemos a corrente por GET.
# Os helpers devolvem a resposta sem afirmar status: cada teste decide o que espera.


async def revisao_do_rascunho(client: AsyncClient, headers: dict[str, str], prompt_id: int) -> int:
    response = await client.get(f"/api/writing/prompts/{prompt_id}/draft", headers=headers)
    assert response.status_code == 200, response.text
    return int(response.json()["revision"])


async def salvar_rascunho(
    client: AsyncClient,
    headers: dict[str, str],
    prompt_id: int,
    text: str,
    *,
    revision: int | None = None,
):
    """PUT do rascunho com a revisão esperada; a resposta traz a nova em `revision`."""
    if revision is None:
        revision = await revisao_do_rascunho(client, headers, prompt_id)
    return await client.put(
        f"/api/writing/prompts/{prompt_id}/draft",
        headers=headers,
        json={"text": text, "expected_revision": revision},
    )


async def criar_versao(
    client: AsyncClient,
    headers: dict[str, str],
    prompt_id: int,
    text: str,
    *,
    revision: int | None = None,
):
    """POST de versão com a revisão esperada; a resposta traz a nova em `draft_revision`."""
    if revision is None:
        revision = await revisao_do_rascunho(client, headers, prompt_id)
    return await client.post(
        f"/api/writing/prompts/{prompt_id}/versions",
        headers=headers,
        json={"text": text, "expected_revision": revision},
    )


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
        "revision": 0,
        "prompt_id": prompt["id"],
        "text": "",
        "updated_at": None,
    }

    first_text = "The Metro is faster than the bus. Visitors should take it."
    salvo = await salvar_rascunho(
        client, headers, prompt["id"], first_text, revision=inicial["revision"]
    )
    assert salvo.status_code == 200
    assert salvo.json()["text"] == first_text
    assert salvo.json()["updated_at"] is not None

    # Cada escrita propaga a revisão devolvida pela anterior, como o cliente faz.
    first_version = await criar_versao(
        client, headers, prompt["id"], first_text, revision=salvo.json()["revision"]
    )
    repeated_version = await criar_versao(
        client, headers, prompt["id"], first_text, revision=first_version.json()["draft_revision"]
    )
    second_text = f"{first_text} It is also more comfortable."
    second_version = await criar_versao(
        client,
        headers,
        prompt["id"],
        second_text,
        revision=repeated_version.json()["draft_revision"],
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
        versions = (await outro_navegador.get(f"{base}/versions", headers=second_headers)).json()

    assert retomado["text"] == second_text
    assert "revisions" not in retomado
    assert [item["version"] for item in versions["items"]] == [2, 1]
    assert versions["next_cursor"] is None


@pytest.mark.asyncio
async def test_rascunho_e_isolado_por_conta(client: AsyncClient) -> None:
    prompt = await proposta(client)
    base = f"/api/writing/prompts/{prompt['id']}"
    ana = await conta(client, "ana")
    assert (
        await salvar_rascunho(client, ana, prompt["id"], "Ana's private draft.")
    ).status_code == 200

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as outro:
        bruno = await conta(outro, "bruno")
        draft = (await outro.get(f"{base}/draft", headers=bruno)).json()
        versions = (await outro.get(f"{base}/versions", headers=bruno)).json()

    assert draft["text"] == ""
    assert "revisions" not in draft
    assert versions["items"] == []


@pytest.mark.timezone
@pytest.mark.asyncio
async def test_paginas_de_escrita_sao_estaveis_pequenas_e_privadas(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    ana = await conta(client, "paginas-ana")
    prompt = await proposta(client)
    base = f"/api/writing/prompts/{prompt['id']}"
    revision: int | None = None
    for number in range(1, 6):
        response = await criar_versao(
            client,
            ana,
            prompt["id"],
            f"Version {number} is intentionally distinct.",
            revision=revision,
        )
        assert response.status_code == 200
        revision = response.json()["draft_revision"]
    for number in range(3):
        response = await client.post(
            f"{base}/feedback",
            headers=ana,
            json={"text": f"Feedback sample {number} is private.", "operation_key": str(uuid4())},
        )
        assert response.status_code == 200

    user = await session.scalar(select(User).where(User.email == "escrita-paginas-ana@exemplo.com"))
    assert user is not None
    draft = await session.scalar(
        select(WritingDraft).where(
            WritingDraft.user_id == user.id,
            WritingDraft.prompt_id == prompt["id"],
        )
    )
    assert draft is not None
    tied_at = datetime(2026, 10, 15, 12, tzinfo=UTC)
    revisions = list(
        (
            await session.execute(
                select(WritingRevision).where(WritingRevision.draft_id == draft.id)
            )
        ).scalars()
    )
    feedbacks = list(
        (
            await session.execute(
                select(WritingFeedbackRecord).where(
                    WritingFeedbackRecord.user_id == user.id,
                    WritingFeedbackRecord.prompt_id == prompt["id"],
                )
            )
        ).scalars()
    )
    for item in [*revisions, *feedbacks]:
        item.created_at = tied_at
    await session.commit()
    monkeypatch.setattr(get_settings(), "performance_probe_enabled", True)

    async def collect(path: str, sql_budget: int) -> list[int]:
        cursor = None
        found: list[int] = []
        while True:
            response = await client.get(
                path,
                headers=ana,
                params={"limit": 2, **({"cursor": cursor} if cursor else {})},
            )
            assert response.status_code == 200
            assert int(response.headers[SQL_HEADER]) <= sql_budget
            assert int(response.headers[POOL_HEADER]) <= 1
            assert int(response.headers[BYTES_HEADER]) == len(response.content)
            body = response.json()
            found.extend(item["id"] for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                return found

    assert await collect(f"{base}/versions", 2) == sorted(
        [item.id for item in revisions], reverse=True
    )
    # Autenticação + página + detecção/carga em lote dos snapshots históricos.
    assert await collect(f"{base}/feedback", 4) == sorted(
        [item.id for item in feedbacks], reverse=True
    )

    current_response = await client.get(f"{base}/draft", headers=ana)
    current = current_response.json()
    assert "revisions" not in current
    assert int(current_response.headers[BYTES_HEADER]) < 1000
    history_response = await client.get(
        "/api/writing/history/page",
        headers=ana,
        params={"course": "voa-level-1", "unit": "31-40", "limit": 1},
    )
    assert int(history_response.headers[SQL_HEADER]) <= 2
    assert int(history_response.headers[POOL_HEADER]) <= 1
    history = history_response.json()
    assert history["next_cursor"] is None
    assert history["items"][0]["revision_count"] == 5
    assert history["items"][0]["feedback_count"] == 3
    assert "draft_text" not in history["items"][0]

    invalid = await client.get(f"{base}/versions?cursor=not-a-cursor", headers=ana)
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_cursor"
    bruno = await conta(client, "paginas-bruno")
    assert (await client.get(f"{base}/versions", headers=bruno)).json()["items"] == []
    assert (await client.get(f"{base}/feedback", headers=bruno)).json()["items"] == []
    assert (await client.get("/api/writing/history/page", headers=bruno)).json()["items"] == []


@pytest.mark.asyncio
async def test_feedback_aponta_pendencias_e_aprova_texto_pronto(client: AsyncClient) -> None:
    headers = await conta(client, "feedback")
    prompt = await proposta(client)
    url = f"/api/writing/prompts/{prompt['id']}/feedback"

    incompleto = (
        await client.post(
            url, headers=headers, json={"text": "bus is fast", "operation_key": str(uuid4())}
        )
    ).json()
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
                ),
                "operation_key": str(uuid4()),
            },
        )
    ).json()
    assert pronto["ready"] is True
    assert pronto["word_count"] >= 35
    assert pronto["sentence_count"] == 4
    assert pronto["algorithm_version"] == "writing-rules-v2"
    assert pronto["rubric_version"].startswith("sha256:")
    assert pronto["rubric_snapshot"]["min_words"] == 35
    assert pronto["rubric_snapshot"]["requirements"][1]["terms"] == ["should", "ought to"]
    assert "Não garante gramática correta" in pronto["evaluation_scope"]
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


async def test_historico_preserva_resultado_e_rubrica_apos_mudar_proposta(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "versionamento")
    prompt = await proposta(client)
    base = f"/api/writing/prompts/{prompt['id']}"
    text = "The bus is faster than the train. You ought to take it."
    assert (await salvar_rascunho(client, headers, prompt["id"], text)).status_code == 200
    first = (
        await client.post(
            f"{base}/feedback", headers=headers, json={"text": text, "operation_key": str(uuid4())}
        )
    ).json()
    assert first["checks"][2]["passed"] is True
    user = (await session.execute(select(User))).scalar_one()
    # Simula um registro legado, sem inventar a rubrica que não era guardada.
    legacy = WritingFeedbackRecord(
        user_id=user.id,
        prompt_id=prompt["id"],
        text="Are you Anna?",
        word_count=3,
        sentence_count=1,
        ready=False,
        checks=[
            {
                "code": "requirement_0",
                "label": "are you",
                "passed": False,
                "suggestion": "Inclua are you.",
            }
        ],
    )
    session.add(legacy)
    await session.commit()
    legacy_id = legacy.id
    stored = await session.get(WritingPrompt, prompt["id"])
    assert stored is not None
    original = deepcopy(stored.requirements)
    try:
        changed = deepcopy(original)
        changed[0]["terms"] = ["slower than"]
        stored.requirements = changed
        await session.commit()
        second = (
            await client.post(
                f"{base}/feedback",
                headers=headers,
                json={"text": text, "operation_key": str(uuid4())},
            )
        ).json()
        assert second["rubric_version"] != first["rubric_version"]
        assert second["checks"][2]["passed"] is False
        history = (await client.get("/api/writing/history", headers=headers)).json()[0]["feedbacks"]
        by_id = {item["id"]: item for item in history}
        assert by_id[first["id"]]["rubric_snapshot"] == first["rubric_snapshot"]
        assert by_id[first["id"]]["checks"] == first["checks"]
        assert by_id[legacy_id]["algorithm_version"] == "legacy-v1"
        assert by_id[legacy_id]["rubric_version"] is None
        assert by_id[legacy_id]["rubric_snapshot"] is None
        assert by_id[legacy_id]["checks"][0]["passed"] is False
        exported = (await client.get("/api/me/export", headers=headers)).json()["writing"][0][
            "feedbacks"
        ]
        assert any(item["rubric_version"] == first["rubric_version"] for item in exported)
        assert any(item["algorithm_version"] == "legacy-v1" for item in exported)
    finally:
        stored.requirements = original
        await session.commit()


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
        json={"text": "The bus is faster.", "assisted": True, "operation_key": str(uuid4())},
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
            json={
                "text": "My draft remains safe.",
                "assisted": True,
                "operation_key": str(uuid4()),
            },
        )
    ).json()
    assert fallback["analysis_mode"] == "fallback"
    assert fallback["assisted_error_code"] == "provider_unavailable"
    assert fallback["checks"]

    quota = (
        await client.post(
            f"/api/writing/prompts/{prompt['id']}/feedback",
            headers=headers,
            json={
                "text": "This draft also remains safe.",
                "assisted": True,
                "operation_key": str(uuid4()),
            },
        )
    ).json()
    assert quota["analysis_mode"] == "fallback"
    assert quota["assisted_error_code"] == "quota_exceeded"


@pytest.mark.asyncio
async def test_feedback_assistido_pode_usar_ollama_local(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def local_feedback(
        base_url: str,
        model: str,
        text: str,
        rubric: list[dict[str, object]],
        *,
        timeout: int,
    ) -> assistance.WritingAssistResult:
        captured.update(
            base_url=base_url,
            model=model,
            text=text,
            rubric=rubric,
            timeout=timeout,
        )
        return assistance.WritingAssistResult(
            summary="Feedback local em português.",
            suggestions=[{"criterion": "word_count", "message": "Acrescente detalhes."}],
            confidence=0.5,
            cost_microusd=0,
        )

    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_provider_kind", "ollama")
    monkeypatch.setattr(settings, "assist_provider_name", "ollama-qwen2.5-7b")
    monkeypatch.setattr(settings, "assist_ollama_base_url", "http://ollama.test:11434")
    monkeypatch.setattr(settings, "assist_ollama_model", "qwen2.5:7b")
    monkeypatch.setattr(assistance, "call_ollama_writing_provider", local_feedback)

    headers = await conta(client, "ollama-local")
    prompt = await proposta(client)
    response = await client.post(
        f"/api/writing/prompts/{prompt['id']}/feedback",
        headers=headers,
        json={
            "text": "The Metro is faster than the bus.",
            "assisted": True,
            "operation_key": str(uuid4()),
        },
    )

    assert response.status_code == 200
    feedback = response.json()
    assert feedback["analysis_mode"] == "assisted"
    assert feedback["provider"] == "ollama-qwen2.5-7b"
    assert feedback["assisted_summary"] == "Feedback local em português."
    assert feedback["assisted_confidence"] == 0.5
    assert feedback["assisted_cost_microusd"] == 0
    rubric = captured["rubric"]
    assert isinstance(rubric, list)
    checks = {item["code"]: item for item in rubric}
    assert checks["word_count"]["passed"] is False
    assert checks["requirement_0"]["passed"] is True
    assert all({"code", "label", "passed", "suggestion"} <= item.keys() for item in rubric)
