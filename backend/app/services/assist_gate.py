"""Gate operacional para liberar os experimentos assistidos.

O relatório usa somente contagens e custo agregado. Texto, áudio, transcrição,
e-mail e qualquer outro conteúdo do aluno não saem do banco nem entram no
arquivo de homologação.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import TranscriptionJob, WritingFeedbackRecord

Modality = Literal["transcription", "writing"]


@dataclass(frozen=True)
class GateMetrics:
    total: int
    successful: int
    failed: int
    rated: int
    helpful: int
    cost_microusd: int

    @property
    def helpful_rate(self) -> float | None:
        return round(self.helpful / self.rated, 4) if self.rated else None

    @property
    def technical_failure_rate(self) -> float | None:
        terminal = self.successful + self.failed
        return round(self.failed / terminal, 4) if terminal else None


@dataclass(frozen=True)
class ProviderReview:
    provider_name: str
    data_processing_agreement: bool
    legal_basis_approved: bool
    region_approved: bool
    provider_retention_days: int | None
    provider_uses_data_for_training: bool | None
    privacy_incidents: int | None
    budget_microusd: int | None
    safety_review_approved: bool
    automation_notice_understood: bool


@dataclass(frozen=True)
class GateReport:
    modality: Modality
    approved: bool
    provider_name: str
    metrics: dict[str, int | float | None]
    criteria: dict[str, bool]
    blocking_reasons: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def load_provider_review(path: Path) -> ProviderReview:
    if path.stat().st_size > 100_000:
        raise ValueError("Manifesto de homologação excede 100 KB.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Manifesto de homologação inválido.") from error
    if not isinstance(raw, dict):
        raise ValueError("Manifesto de homologação precisa ser um objeto JSON.")

    def boolean(name: str) -> bool:
        value = raw.get(name)
        if not isinstance(value, bool):
            raise ValueError(f"{name} precisa ser booleano.")
        return value

    def optional_int(name: str) -> int | None:
        value = raw.get(name)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} precisa ser inteiro não negativo ou null.")
        return value

    provider_name = raw.get("provider_name")
    provider_uses_data_for_training = raw.get("provider_uses_data_for_training")
    if not isinstance(provider_name, str) or not provider_name.strip():
        raise ValueError("provider_name precisa ser preenchido.")
    if provider_uses_data_for_training is not None and not isinstance(
        provider_uses_data_for_training, bool
    ):
        raise ValueError("provider_uses_data_for_training precisa ser booleano ou null.")

    return ProviderReview(
        provider_name=provider_name.strip(),
        data_processing_agreement=boolean("data_processing_agreement"),
        legal_basis_approved=boolean("legal_basis_approved"),
        region_approved=boolean("region_approved"),
        provider_retention_days=optional_int("provider_retention_days"),
        provider_uses_data_for_training=provider_uses_data_for_training,
        privacy_incidents=optional_int("privacy_incidents"),
        budget_microusd=optional_int("budget_microusd"),
        safety_review_approved=boolean("safety_review_approved"),
        automation_notice_understood=boolean("automation_notice_understood"),
    )


async def collect_gate_metrics(session: AsyncSession, modality: Modality) -> GateMetrics:
    if modality == "transcription":
        row = (
            await session.execute(
                select(
                    func.count(TranscriptionJob.id),
                    func.count(TranscriptionJob.id).filter(TranscriptionJob.status == "completed"),
                    func.count(TranscriptionJob.id).filter(TranscriptionJob.status == "failed"),
                    func.count(TranscriptionJob.id).filter(
                        TranscriptionJob.status == "completed",
                        TranscriptionJob.human_rating.is_not(None),
                    ),
                    func.count(TranscriptionJob.id).filter(
                        TranscriptionJob.status == "completed",
                        TranscriptionJob.human_rating == "helpful",
                    ),
                    func.coalesce(func.sum(TranscriptionJob.cost_microusd), 0),
                )
            )
        ).one()
    else:
        assisted = WritingFeedbackRecord.provider.is_not(None)
        row = (
            await session.execute(
                select(
                    func.count(WritingFeedbackRecord.id).filter(assisted),
                    func.count(WritingFeedbackRecord.id).filter(
                        assisted, WritingFeedbackRecord.analysis_mode == "assisted"
                    ),
                    func.count(WritingFeedbackRecord.id).filter(
                        assisted, WritingFeedbackRecord.analysis_mode == "fallback"
                    ),
                    func.count(WritingFeedbackRecord.id).filter(
                        assisted,
                        WritingFeedbackRecord.analysis_mode == "assisted",
                        WritingFeedbackRecord.human_rating.is_not(None),
                    ),
                    func.count(WritingFeedbackRecord.id).filter(
                        assisted,
                        WritingFeedbackRecord.analysis_mode == "assisted",
                        WritingFeedbackRecord.human_rating == "helpful",
                    ),
                    func.coalesce(
                        func.sum(WritingFeedbackRecord.assisted_cost_microusd).filter(assisted), 0
                    ),
                )
            )
        ).one()

    return GateMetrics(
        total=int(row[0]),
        successful=int(row[1]),
        failed=int(row[2]),
        rated=int(row[3]),
        helpful=int(row[4]),
        cost_microusd=int(row[5]),
    )


def evaluate_gate(
    modality: Modality,
    metrics: GateMetrics,
    review: ProviderReview,
    settings: Settings,
) -> GateReport:
    provider_configured = (
        bool(settings.assist_transcription_url)
        if modality == "transcription"
        else settings.writing_assist_configured
    )
    criteria = {
        "provider_configured": provider_configured,
        "provider_name_matches": review.provider_name == settings.assist_provider_name,
        "data_processing_agreement": review.data_processing_agreement,
        "legal_basis_approved": review.legal_basis_approved,
        "region_approved": review.region_approved,
        "retention_compatible": review.provider_retention_days is not None
        and review.provider_retention_days <= settings.assist_retention_days,
        "provider_training_disabled": review.provider_uses_data_for_training is False,
        "no_privacy_incidents": review.privacy_incidents == 0,
        "budget_defined": review.budget_microusd is not None,
        "within_budget": review.budget_microusd is not None
        and metrics.cost_microusd <= review.budget_microusd,
        "minimum_human_ratings": metrics.rated >= 30,
        "helpful_rate": metrics.helpful_rate is not None and metrics.helpful_rate >= 0.8,
        "technical_failure_rate": metrics.technical_failure_rate is not None
        and metrics.technical_failure_rate < 0.05,
        "safety_review_approved": review.safety_review_approved,
        "automation_notice_understood": review.automation_notice_understood,
    }
    reasons = [name for name, passed in criteria.items() if not passed]
    return GateReport(
        modality=modality,
        approved=not reasons,
        provider_name=review.provider_name,
        metrics={
            **asdict(metrics),
            "helpful_rate": metrics.helpful_rate,
            "technical_failure_rate": metrics.technical_failure_rate,
        },
        criteria=criteria,
        blocking_reasons=reasons,
    )
