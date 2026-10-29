from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    AssistReservation,
    DialogueTurn,
    Lesson,
    SpeakingDialogue,
    User,
)
from app.services import operations_metrics
from app.services.assist_quota import DIALOGUE_MODALITY
from app.services.dialogue_prompts import PROMPT_VERSION

TOKEN = "operations-test-token-with-at-least-32-bytes"


@pytest.mark.asyncio
async def test_metrics_desabilitadas_parecem_recurso_ausente(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "operations_token", None)
    response = await client.get("/api/operations/metrics")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_metrics_exigem_bearer_sem_refletir_credencial(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "operations_token", TOKEN)
    response = await client.get(
        "/api/operations/metrics",
        headers={"Authorization": "Bearer credencial-privada-incorreta"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "credencial-privada" not in response.text


@pytest.mark.asyncio
async def test_metrics_agregadas_tem_cardinalidade_fixa_e_nenhum_conteudo(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "operations_token", TOKEN)
    monkeypatch.setattr(operations_metrics, "_disk_metrics", lambda path: (True, 10_000, 4_000))
    response = await client.get(
        "/api/operations/metrics",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert set(body) == {
        "sampled_at",
        "requests",
        "database",
        "transcription_queue",
        "dialogue",
        "assist_costs",
        "account_deletions",
        "legacy_review",
        "media",
    }
    assert set(body["requests"]["latency_buckets_ms"]) == {
        "50",
        "100",
        "250",
        "500",
        "1000",
        "2500",
        "5000",
        "+Inf",
    }
    assert body["requests"]["scope"] == "process"
    assert body["database"]["size_bytes"] > 0
    assert len(body["database"]["largest_relations"]) <= 5
    assert all(
        set(item) == {"relation", "total_bytes"} for item in body["database"]["largest_relations"]
    )
    assert body["media"]["filesystem_capacity_bytes"] == 10_000
    assert body["media"]["filesystem_free_bytes"] == 4_000
    assert body["legacy_review"]["unlinked_cards"] == 0
    assert body["legacy_review"]["mismatched_links"] == 0
    assert set(body["assist_costs"]) == {"daily", "monthly"}
    assert body["assist_costs"]["daily"]["cost_microusd"] == 0
    serialized = response.text.lower()
    for forbidden in ("email", "transcript_text", "storage_key", "authorization", TOKEN.lower()):
        assert forbidden not in serialized


@pytest.mark.timezone
@pytest.mark.asyncio
async def test_metrica_de_dialogo_conta_o_dia_sem_dizer_o_que_foi_falado(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INFRA-46: turnos, p95, falhas, custo e cota — e nenhum texto.

    O turno do parceiro não entra em `turns`: ele vive na mesma linha do turno
    do aluno, e contar as duas pontas dobraria o número que o painel compara
    com a cota.
    """
    monkeypatch.setattr(get_settings(), "operations_token", TOKEN)
    agora = datetime.now(UTC)
    user = User(email="metrica-dialogo@example.com", password_hash="x", display_name="Metrica")
    session.add(user)
    await session.flush()
    lesson = (await session.execute(select(Lesson).limit(1))).scalar_one()
    dialogo = SpeakingDialogue(
        user_id=user.id,
        lesson_id=lesson.id,
        operation_key=str(uuid4()),
        mode="guided",
        state="active",
        partner_speaker="Anna",
        content_version=lesson.id,
        content_fingerprint="f" * 64,
        provider_name="provedor",
        rubric_version=PROMPT_VERSION,
        turn_limit=12,
        started_at=agora,
    )
    session.add(dialogo)
    await session.flush()
    # Dois turnos prontos (2 s e 6 s), um que falhou e um do parceiro.
    for posicao, (segundos, state, erro, fallback, custo) in enumerate(
        [
            (2, "completed", None, False, 40),
            (6, "completed", None, True, 0),
            (None, "failed", "provider_unavailable", False, 7),
        ],
        start=1,
    ):
        session.add(
            DialogueTurn(
                dialogue_id=dialogo.id,
                user_id=user.id,
                position=posicao,
                role="student",
                input_kind="text",
                state=state,
                transcript="I take the subway to the stadium every day.",
                partner_text="Nice. Is it faster than the bus?",
                fallback=fallback,
                error_code=erro,
                cost_microusd=custo,
                created_at=agora,
                completed_at=agora + timedelta(seconds=segundos) if segundos else None,
                expires_at=agora + timedelta(days=30),
            )
        )
    session.add(
        DialogueTurn(
            dialogue_id=dialogo.id,
            user_id=user.id,
            position=4,
            role="partner",
            state="completed",
            partner_text="See you at the game!",
            created_at=agora,
            completed_at=agora,
            expires_at=agora + timedelta(days=30),
        )
    )
    await session.commit()

    response = await client.get(
        "/api/operations/metrics", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200, response.text
    dialogue = response.json()["dialogue"]
    assert dialogue["turns"] == 3
    assert dialogue["completed"] == 2
    assert dialogue["failed"] == 1
    assert dialogue["fallback"] == 1
    assert dialogue["provider_failures"] == 1
    assert dialogue["cost_microusd"] == 47
    # p95 entre 2 s e 6 s fica perto do maior; o contrato é o valor em ms.
    assert dialogue["latency_p95_ms"] is not None
    assert 2_000 <= dialogue["latency_p95_ms"] <= 6_000
    assert dialogue["quota_limit"] == get_settings().assist_dialogue_daily_turns
    assert dialogue["quota_used"] == 0
    assert dialogue["quota_exhausted_accounts"] == 0
    # Nem a transcrição, nem a fala do parceiro, nem a conta aparecem.
    serializado = response.text.lower()
    for proibido in ("subway", "stadium", "faster than the bus", "metrica-dialogo"):
        assert proibido not in serializado


@pytest.mark.timezone
@pytest.mark.asyncio
async def test_cota_de_conversa_no_painel_usa_a_mesma_conta_do_429(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reservado válido + consumido, como em `assist_quota.usage`.

    Duas definições de consumo divergiriam na primeira mudança de regra, e o
    painel passaria a discordar do 429 que o aluno recebeu.
    """
    monkeypatch.setattr(get_settings(), "operations_token", TOKEN)
    limite = get_settings().assist_dialogue_daily_turns
    agora = datetime.now(UTC)
    user = User(email="cota-painel@example.com", password_hash="x", display_name="Cota")
    session.add(user)
    await session.flush()
    for indice in range(limite):
        session.add(
            AssistReservation(
                user_id=user.id,
                request_key=f"turno-{indice}",
                fingerprint=f"{indice:064d}",
                modality=DIALOGUE_MODALITY,
                provider_key=str(uuid4()),
                state="consumed",
                cost_microusd=3,
                cost_known=True,
                created_at=agora,
                expires_at=agora + timedelta(hours=1),
            )
        )
    # Reserva expirada não conta: ela voltou para o orçamento. O banco exige
    # `expires_at > created_at` (`ck_assist_expiry`), então ela nasce no
    # passado. Perto da meia-noite UTC ela cai no dia anterior e sai da conta
    # pelo recorte do dia — a afirmação é a mesma nos dois casos.
    session.add(
        AssistReservation(
            user_id=user.id,
            request_key="expirada",
            fingerprint="e" * 64,
            modality=DIALOGUE_MODALITY,
            provider_key=str(uuid4()),
            state="reserved",
            created_at=agora - timedelta(minutes=10),
            expires_at=agora - timedelta(minutes=5),
        )
    )
    await session.commit()

    response = await client.get(
        "/api/operations/metrics", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    dialogue = response.json()["dialogue"]
    assert dialogue["quota_used"] == limite
    assert dialogue["quota_exhausted_accounts"] == 1
    assert "cota-painel" not in response.text.lower()


@pytest.mark.timezone
@pytest.mark.parametrize("timezone", ["UTC", "Pacific/Kiritimati"])
async def test_custo_diario_mensal_usa_ledger_e_despacho_em_utc(session, timezone):
    # O fuso da conexão não pode mudar o mês/dia do painel.
    await session.execute(text("SELECT set_config('TimeZone', :tz, true)"), {"tz": timezone})
    now = datetime(2026, 3, 10, 1, tzinfo=UTC)
    yesterday = now - timedelta(days=1)
    user = User(email="cost-private@example.test", password_hash="x", display_name="Private")
    session.add(user)
    await session.flush()
    rows = [
        ("conversation", "consumed", yesterday, now, 10, True),
        ("writing", "consumed", yesterday, yesterday, 20, True),
        ("transcription", "consumed", now, now, 7, False),
        ("conversation", "consumed", now, now, 0, True),
        ("conversation", "consumed", now, None, 3, True),  # legado
        ("writing", "reserved", now, None, 900, False),
        ("writing", "released", now, None, 900, True),
        ("writing", "consumed", now - timedelta(days=31), now - timedelta(days=31), 900, True),
        ("writing", "consumed", now + timedelta(hours=1), now + timedelta(hours=1), 900, True),
    ]
    for modality, state, created, dispatched, cost, known in rows:
        session.add(
            AssistReservation(
                user_id=user.id,
                request_key=str(uuid4()),
                fingerprint="f" * 64,
                modality=modality,
                provider_key=str(uuid4()),
                state=state,
                cost_microusd=cost,
                cost_known=known,
                created_at=created,
                expires_at=created + timedelta(hours=1),
                dispatched_at=dispatched,
            )
        )
    await session.flush()
    # Não há turno/job: excluir resultados ou expirar texto não zera o ledger.
    result = await operations_metrics._assist_costs(session, now)
    assert result.daily.consumed == 4 and result.daily.cost_microusd == 20
    assert result.monthly.consumed == 5 and result.monthly.cost_microusd == 40
    assert result.daily.unknown_cost_reservations == result.monthly.unknown_cost_reservations == 1
    assert result.daily.starts_at == datetime(2026, 3, 10, tzinfo=UTC)
    assert result.daily.ends_at == datetime(2026, 3, 11, tzinfo=UTC)
    assert result.monthly.starts_at == datetime(2026, 3, 1, tzinfo=UTC)
    assert result.monthly.ends_at == datetime(2026, 4, 1, tzinfo=UTC)
    assert user.email not in result.model_dump_json()


@pytest.mark.timezone
@pytest.mark.parametrize(
    ("now", "end"),
    [
        (datetime(2024, 2, 29, tzinfo=UTC), datetime(2024, 3, 1, tzinfo=UTC)),
        (datetime(2026, 12, 31, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)),
    ],
)
async def test_janela_de_custo_usa_mes_calendario(session, now, end):
    result = await operations_metrics._assist_costs(session, now)
    assert result.monthly.ends_at == end
    assert result.monthly.consumed == result.monthly.cost_microusd == 0
