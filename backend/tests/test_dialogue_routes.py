"""Rotas do parceiro de conversa: posse, idempotência e os códigos de erro.

O que importa provar aqui não é que a rota responde, é que ela responde o
**mesmo** quando é reenviada e que não conta nada sobre a conta de outro aluno.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services import assistance
from tests.test_auth import auth, registrar


async def _aula_id(client: AsyncClient) -> int:
    return int((await client.get("/api/lessons/31")).json()["id"])


async def _criar(
    client: AsyncClient, headers: dict[str, str], *, mode: str = "script", **extra: object
) -> tuple[int, dict[str, object]]:
    corpo = {
        "lesson_id": await _aula_id(client),
        "mode": mode,
        "operation_key": str(uuid4()),
        **extra,
    }
    resposta = await client.post("/api/speaking/dialogues", headers=headers, json=corpo)
    return resposta.status_code, resposta.json()


@pytest.mark.asyncio
async def test_roteiro_abre_conversa_e_fecha_o_turno_na_hora(client: AsyncClient) -> None:
    headers = auth(await registrar(client, "dialogo-roteiro"))
    codigo, corpo = await _criar(client, headers)
    assert codigo == 201, corpo
    assert corpo["mode"] == "script"
    assert corpo["turn_limit"] == 12 and corpo["turns_remaining"] == 12
    assert corpo["provider_name"] is None

    dialogo_id = corpo["id"]
    turno = await client.post(
        f"/api/speaking/dialogues/{dialogo_id}/turns/1/text",
        headers=headers,
        json={"text": "The train is faster than the bus.", "idempotency_key": str(uuid4())},
    )
    assert turno.status_code == 202, turno.text
    # Roteiro não passa pela fila: sem job, resolvido na própria requisição.
    assert turno.json()["job_id"] is None
    assert turno.json()["state"] == "completed"
    assert turno.json()["turns_remaining"] == 11

    detalhe = (
        await client.get(f"/api/speaking/dialogues/{dialogo_id}/turns/1", headers=headers)
    ).json()
    assert detalhe["partner_text"]
    # `checks` é mapa código→cumpriu, nunca nota nem percentual.
    assert detalhe["checks"] and all(isinstance(v, bool) for v in detalhe["checks"].values())
    assert detalhe["fallback"] is False and detalhe["hints"] == []


@pytest.mark.asyncio
async def test_criacao_e_turno_sao_idempotentes_pela_chave(client: AsyncClient) -> None:
    headers = auth(await registrar(client, "dialogo-idem"))
    chave = str(uuid4())
    corpo = {"lesson_id": await _aula_id(client), "mode": "script", "operation_key": chave}
    primeiro = await client.post("/api/speaking/dialogues", headers=headers, json=corpo)
    segundo = await client.post("/api/speaking/dialogues", headers=headers, json=corpo)
    assert primeiro.json()["id"] == segundo.json()["id"]

    dialogo_id = primeiro.json()["id"]
    turno = {"text": "I take the bus every day.", "idempotency_key": str(uuid4())}
    a = await client.post(
        f"/api/speaking/dialogues/{dialogo_id}/turns/1/text", headers=headers, json=turno
    )
    b = await client.post(
        f"/api/speaking/dialogues/{dialogo_id}/turns/1/text", headers=headers, json=turno
    )
    assert a.status_code == b.status_code == 202
    # Idempotência pelo par (dialogue_id, position): o reenvio não cria turno
    # novo nem consome outro do limite.
    assert a.json()["turns_remaining"] == b.json()["turns_remaining"] == 11


@pytest.mark.asyncio
async def test_dialogo_de_outra_conta_responde_404_e_nao_403(client: AsyncClient) -> None:
    dono = auth(await registrar(client, "dialogo-dono"))
    _, corpo = await _criar(client, dono)
    alheio = auth(await registrar(client, "dialogo-alheio"))
    dialogo_id = corpo["id"]

    # 404 em todas as rotas: 403 contaria que o diálogo existe.
    assert (
        await client.get(f"/api/speaking/dialogues/{dialogo_id}", headers=alheio)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/speaking/dialogues/{dialogo_id}/turns/1/text",
            headers=alheio,
            json={"text": "Not mine.", "idempotency_key": str(uuid4())},
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/speaking/dialogues/{dialogo_id}", headers=alheio)
    ).status_code == 404
    # E o dono continua com o diálogo intacto.
    assert (
        await client.get(f"/api/speaking/dialogues/{dialogo_id}", headers=dono)
    ).status_code == 200


@pytest.mark.asyncio
async def test_modo_com_ia_desligado_responde_409_assist_disabled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "assisted_features_enabled", False)
    headers = auth(await registrar(client, "dialogo-off"))
    codigo, corpo = await _criar(client, headers, mode="guided")
    # 409 e não 503: não é queda momentânea, é modo desligado nesta instalação.
    assert codigo == 409
    assert corpo["detail"]["code"] == "assist_disabled"
    # E o Roteiro segue disponível, que é a saída que o cliente deve oferecer.
    assert (await _criar(client, headers))[0] == 201


@pytest.mark.asyncio
async def test_guiado_enfileira_o_turno_e_a_cota_recusa_o_dialogo_seguinte(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_provider_kind", "gateway")
    monkeypatch.setattr(settings, "assist_dialogue_url", "https://provedor/invalido")
    monkeypatch.setattr(settings, "assist_dialogue_daily_turns", 12)

    def nunca(*args: object, **kwargs: object) -> assistance.DialogueResult:
        raise AssertionError("a API não chama o provedor: quem chama é o worker")

    monkeypatch.setattr(assistance, "call_dialogue_provider", nunca)
    headers = auth(await registrar(client, "dialogo-cota"))
    _, corpo = await _criar(client, headers, mode="guided")
    dialogo_id = corpo["id"]
    assert corpo["provider_name"]

    for posicao in range(1, 13):
        resposta = await client.post(
            f"/api/speaking/dialogues/{dialogo_id}/turns/{posicao}/text",
            headers=headers,
            json={"text": "I took the train today.", "idempotency_key": str(uuid4())},
        )
        assert resposta.status_code == 202, resposta.text
        # Guiado passa pela fila: o provedor roda no worker, não na requisição.
        assert resposta.json()["job_id"] is not None
        assert resposta.json()["state"] == "pending"

    # Acima do limite: a resposta é "este diálogo terminou", não "cota".
    excedente = await client.post(
        f"/api/speaking/dialogues/{dialogo_id}/turns/13/text",
        headers=headers,
        json={"text": "One more.", "idempotency_key": str(uuid4())},
    )
    assert excedente.status_code == 409
    assert excedente.json()["detail"]["code"] == "dialogue_turn_limit"

    # A cota aparece no diálogo seguinte, com 429.
    _, outro = await _criar(client, headers, mode="guided")
    esgotado = await client.post(
        f"/api/speaking/dialogues/{outro['id']}/turns/1/text",
        headers=headers,
        json={"text": "Starting again.", "idempotency_key": str(uuid4())},
    )
    assert esgotado.status_code == 429
    assert esgotado.json()["detail"]["code"] == "assist_quota_exceeded"


@pytest.mark.asyncio
async def test_avaliacao_humana_e_o_unico_campo_que_a_api_altera(
    client: AsyncClient,
) -> None:
    headers = auth(await registrar(client, "dialogo-nota"))
    _, corpo = await _criar(client, headers)
    dialogo_id = corpo["id"]
    await client.post(
        f"/api/speaking/dialogues/{dialogo_id}/turns/1/text",
        headers=headers,
        json={"text": "The bus is cheaper than the train.", "idempotency_key": str(uuid4())},
    )
    avaliado = await client.put(
        f"/api/speaking/dialogues/{dialogo_id}/turns/1/rating",
        headers=headers,
        json={"rating": "helpful"},
    )
    assert avaliado.status_code == 200
    assert avaliado.json()["human_rating"] == "helpful"


@pytest.mark.asyncio
async def test_exclusao_leva_os_turnos_e_a_conversa_deixa_de_existir(
    client: AsyncClient,
) -> None:
    headers = auth(await registrar(client, "dialogo-exclusao"))
    _, corpo = await _criar(client, headers)
    dialogo_id = corpo["id"]
    await client.post(
        f"/api/speaking/dialogues/{dialogo_id}/turns/1/text",
        headers=headers,
        json={"text": "Something to remember.", "idempotency_key": str(uuid4())},
    )
    assert (
        await client.delete(f"/api/speaking/dialogues/{dialogo_id}", headers=headers)
    ).status_code == 204
    # Turnos vão por cascata do PostgreSQL, não por laço da aplicação.
    assert (
        await client.get(f"/api/speaking/dialogues/{dialogo_id}", headers=headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/speaking/dialogues/{dialogo_id}/turns/1", headers=headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_aula_nao_publicada_nao_abre_conversa(client: AsyncClient) -> None:
    headers = auth(await registrar(client, "dialogo-nao-publicada"))
    resposta = await client.post(
        "/api/speaking/dialogues",
        headers=headers,
        json={"lesson_id": 999_999, "mode": "script", "operation_key": str(uuid4())},
    )
    assert resposta.status_code == 404


@pytest.mark.asyncio
async def test_rotas_do_dialogo_nao_cacheiam(client: AsyncClient) -> None:
    headers = auth(await registrar(client, "dialogo-cache"))
    _, corpo = await _criar(client, headers)
    resposta = await client.get(f"/api/speaking/dialogues/{corpo['id']}", headers=headers)
    assert resposta.headers["cache-control"] == "private, no-store"
