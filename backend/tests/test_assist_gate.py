"""Gate humano e de privacidade dos provedores assistidos."""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
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


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"assist_timeout_seconds": 0}, "ASSIST_TIMEOUT_SECONDS"),
        ({"assist_provider_name": ""}, "ASSIST_PROVIDER_NAME"),
        ({"assist_provider_name": "x" * 81}, "ASSIST_PROVIDER_NAME"),
        (
            {"assist_provider_kind": "ollama", "assist_ollama_base_url": "arquivo-local"},
            "ASSIST_OLLAMA_BASE_URL",
        ),
        (
            {"assist_provider_kind": "ollama", "assist_ollama_model": ""},
            "ASSIST_OLLAMA_MODEL",
        ),
    ],
)
def test_configuracao_assistida_recusa_limites_invalidos(
    overrides: dict[str, object], message: str
) -> None:
    settings = Settings(**overrides)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match=message):
        settings.validar()
