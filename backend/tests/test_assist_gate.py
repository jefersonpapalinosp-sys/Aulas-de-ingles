"""Gate humano e de privacidade dos provedores assistidos."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.dialogue import MAX_TURNS_PER_DIALOGUE
from app.services.assist_gate import (
    GateMetrics,
    ProviderReview,
    evaluate_gate,
    load_provider_review,
)


def approved_review() -> ProviderReview:
    return ProviderReview(
        provider_name="pilot-provider",
        data_processing_agreement=True,
        legal_basis_approved=True,
        region_approved=True,
        provider_retention_days=15,
        provider_uses_data_for_training=False,
        privacy_incidents=0,
        budget_microusd=1_000,
        safety_review_approved=True,
        automation_notice_understood=True,
    )


def test_gate_aprova_somente_com_metricas_e_revisao_completas() -> None:
    settings = Settings(
        assist_provider_name="pilot-provider",
        assist_writing_url="https://gateway.example/writing",
        assist_retention_days=30,
    )
    metrics = GateMetrics(
        total=31,
        successful=30,
        failed=1,
        rated=30,
        helpful=24,
        cost_microusd=900,
    )

    report = evaluate_gate("writing", metrics, approved_review(), settings)

    assert report.approved is True
    assert report.blocking_reasons == []
    assert report.metrics["helpful_rate"] == 0.8
    assert report.metrics["technical_failure_rate"] == pytest.approx(0.0323)


def test_gate_lista_bloqueios_sem_liberar_feature_flag() -> None:
    settings = Settings(assist_provider_name="external", assist_retention_days=30)
    review = ProviderReview(
        provider_name="candidate",
        data_processing_agreement=False,
        legal_basis_approved=False,
        region_approved=False,
        provider_retention_days=None,
        provider_uses_data_for_training=None,
        privacy_incidents=None,
        budget_microusd=None,
        safety_review_approved=False,
        automation_notice_understood=False,
    )

    report = evaluate_gate(
        "transcription",
        GateMetrics(total=0, successful=0, failed=0, rated=0, helpful=0, cost_microusd=0),
        review,
        settings,
    )

    assert report.approved is False
    assert "provider_configured" in report.blocking_reasons
    assert "minimum_human_ratings" in report.blocking_reasons
    assert "no_privacy_incidents" in report.blocking_reasons
    assert "budget_defined" in report.blocking_reasons


def test_manifesto_rejeita_campos_de_privacidade_ambiguos(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    payload = {
        "provider_name": "candidate",
        "data_processing_agreement": True,
        "legal_basis_approved": True,
        "region_approved": True,
        "provider_retention_days": 10,
        "provider_uses_data_for_training": "unknown",
        "privacy_incidents": 0,
        "budget_microusd": 100,
        "safety_review_approved": True,
        "automation_notice_understood": True,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="provider_uses_data_for_training"):
        load_provider_review(path)


def conversation_metrics() -> GateMetrics:
    return GateMetrics(30, 30, 0, 30, 24, 900, rated_lessons=5)


def test_conversation_usa_configuracao_propria_e_nao_ativa_flags() -> None:
    review = replace(approved_review(), modality="conversation")
    settings = Settings(
        assist_provider_name="pilot-provider",
        assist_writing_url="https://gateway.example/writing",
    )
    report = evaluate_gate("conversation", conversation_metrics(), review, settings)
    assert report.blocking_reasons == ["provider_configured"]
    settings.assist_dialogue_url = "https://gateway.example/dialogue"
    settings.assist_writing_url = None
    assert evaluate_gate("conversation", conversation_metrics(), review, settings).approved
    assert not settings.assisted_features_enabled
    assert not settings.dialogue_practice_enabled


@pytest.mark.parametrize("modality", [None, "writing", "transcription"])
def test_conversation_nao_reutiliza_manifesto_de_outra_modalidade(modality) -> None:
    report = evaluate_gate(
        "conversation",
        conversation_metrics(),
        replace(approved_review(), modality=modality),
        Settings(assist_provider_name="pilot-provider", assist_dialogue_url="https://example.test"),
    )
    assert report.blocking_reasons == ["review_modality_matches"]


@pytest.mark.parametrize(
    ("metrics", "reason"),
    [
        (replace(conversation_metrics(), rated_lessons=4), "minimum_rated_lessons"),
        (replace(conversation_metrics(), unknown_cost_turns=1), "cost_known"),
        (replace(conversation_metrics(), cost_microusd=1001), "within_budget"),
        (replace(conversation_metrics(), successful=38, failed=2), "technical_failure_rate"),
        (replace(conversation_metrics(), rated=29), "minimum_human_ratings"),
        # 79,999% arredonda para 80%; o gate deve recusar mesmo assim.
        (replace(conversation_metrics(), rated=100_000, helpful=79_999), "helpful_rate"),
    ],
)
def test_conversation_recusa_evidencia_insuficiente(metrics, reason) -> None:
    report = evaluate_gate(
        "conversation",
        metrics,
        replace(approved_review(), modality="conversation"),
        Settings(assist_provider_name="pilot-provider", assist_dialogue_url="https://example.test"),
    )
    assert reason in report.blocking_reasons and not report.approved


def test_limiar_de_falha_nao_arredonda_antes_de_decidir() -> None:
    metrics = replace(conversation_metrics(), successful=95_001, failed=4_999)
    report = evaluate_gate(
        "conversation",
        metrics,
        replace(approved_review(), modality="conversation"),
        Settings(assist_provider_name="pilot-provider", assist_dialogue_url="https://example.test"),
    )
    assert report.metrics["technical_failure_rate"] == 0.05
    assert report.approved  # 4,999% é estritamente menor que 5%.


def test_manifesto_exemplo_conversation_falha_fechado() -> None:
    review = load_provider_review(
        Path(__file__).resolve().parents[2] / "config/assist-provider-review.example.json"
    )
    assert review.modality == "conversation"
    report = evaluate_gate("conversation", conversation_metrics(), review, Settings())
    assert not report.approved
    assert "region_approved" in report.blocking_reasons
    assert "provider_training_disabled" in report.blocking_reasons
    assert "retention_compatible" in report.blocking_reasons


@pytest.mark.parametrize("modality", ["invalid", [], {}])
def test_manifesto_rejeita_modalidade_invalida(tmp_path, modality) -> None:
    path = tmp_path / "review.json"
    path.write_text(json.dumps({"modality": modality}))
    with pytest.raises(ValueError, match="modality"):
        load_provider_review(path)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"assist_timeout_seconds": 0}, "ASSIST_TIMEOUT_SECONDS"),
        ({"assist_reservation_seconds": 59}, "ASSIST_RESERVATION_SECONDS"),
        ({"assist_reservation_seconds": 3601}, "ASSIST_RESERVATION_SECONDS"),
        ({"assist_job_max_attempts": 0}, "ASSIST_JOB_MAX_ATTEMPTS"),
        ({"assist_job_retry_base_seconds": -1}, "ASSIST_JOB_RETRY_BASE_SECONDS"),
        (
            {"assist_timeout_seconds": 20, "assist_job_stale_seconds": 19},
            "ASSIST_JOB_STALE_SECONDS",
        ),
        ({"assist_worker_poll_seconds": 0}, "ASSIST_WORKER_POLL_SECONDS"),
        ({"assist_provider_name": ""}, "ASSIST_PROVIDER_NAME"),
        ({"assist_provider_name": "x" * 81}, "ASSIST_PROVIDER_NAME"),
        (
            {"database_statement_timeout_ms": 5_000, "database_lock_timeout_ms": 5_000},
            "DATABASE_LOCK_TIMEOUT_MS",
        ),
        (
            {"assist_provider_kind": "ollama", "assist_ollama_base_url": "arquivo-local"},
            "ASSIST_OLLAMA_BASE_URL",
        ),
        (
            {"assist_provider_kind": "ollama", "assist_ollama_model": ""},
            "ASSIST_OLLAMA_MODEL",
        ),
        # A cota de conversa é "dois diálogos completos", não um número: 20
        # turnos com limite de 12 por diálogo daria 429 no turno 8 do segundo,
        # no meio da conversa. O boot recusa em vez de deixar isso acontecer.
        ({"assist_dialogue_daily_turns": 20}, "múltiplo de 12"),
        ({"assist_dialogue_daily_turns": 6}, "múltiplo de 12"),
    ],
)
def test_configuracao_assistida_recusa_limites_invalidos(
    overrides: dict[str, object], message: str
) -> None:
    settings = Settings(**overrides)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match=message):
        settings.validar()


@pytest.mark.parametrize(
    "overrides",
    [
        # SEC-46: a URL do diálogo entrou no BE-46 e ficou fora do gate de
        # produção. Sem estes casos, o texto do aluno poderia sair em HTTP
        # puro, ou sem token, e o boot não reclamaria.
        # URL sem TLS, com token presente: reprova pelo HTTPS.
        {"assist_dialogue_url": "http://provedor.invalido/dialogo", "assist_provider_token": "x"},
        # URL com TLS, sem token: reprova pelo token.
        {"assist_dialogue_url": "https://provedor.invalido/dialogo"},
    ],
)
def test_producao_recusa_provedor_de_dialogo_sem_https_ou_sem_token(
    overrides: dict[str, object],
) -> None:
    settings = Settings(  # type: ignore[arg-type]
        app_env="prod",
        jwt_secret="segredo-de-producao-para-o-teste",
        cookie_secure=True,
        public_origin="https://aulas.exemplo.test",
        assisted_features_enabled=True,
        **overrides,
    )
    with pytest.raises(RuntimeError, match="HTTPS em produção|ASSIST_PROVIDER_TOKEN"):
        settings.validar()


def test_producao_aceita_provedor_de_dialogo_com_https_e_token() -> None:
    settings = Settings(  # type: ignore[arg-type]
        app_env="prod",
        jwt_secret="segredo-de-producao-para-o-teste",
        cookie_secure=True,
        public_origin="https://aulas.exemplo.test",
        assisted_features_enabled=True,
        assist_dialogue_url="https://provedor.exemplo.test/dialogo",
        assist_provider_token="segredo",
    )
    settings.validar()


@pytest.mark.parametrize("turnos", [12, 24, 36])
def test_cota_de_conversa_aceita_multiplos_do_limite_do_dialogo(turnos: int) -> None:
    """Qualquer múltiplo serve; o que a decisão fixou foi a relação, não o 24."""
    settings = Settings(assist_dialogue_daily_turns=turnos)  # type: ignore[arg-type]
    settings.validar()
    assert settings.assist_dialogue_daily_turns % MAX_TURNS_PER_DIALOGUE == 0
