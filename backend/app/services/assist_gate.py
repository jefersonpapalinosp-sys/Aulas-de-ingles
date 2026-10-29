"""Gate operacional para liberar os experimentos assistidos.

O relatório usa somente contagens e custo agregado. Texto, áudio, transcrição,
e-mail e qualquer outro conteúdo do aluno não saem do banco nem entram no
arquivo de homologação.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import get_args

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import (
    AssistReservation,
    DialogueTurn,
    SpeakingDialogue,
    TranscriptionJob,
    WritingFeedbackRecord,
)
from app.domain.enums import AssistModality

# Conjunto único em app/domain/enums.py; o nome local é mantido.
Modality = AssistModality


@dataclass(frozen=True)
class GateMetrics:
    total: int
    successful: int
    failed: int
    rated: int
    helpful: int
    cost_microusd: int
    rated_lessons: int = 0
    unknown_cost_turns: int = 0

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
    modality: Modality | None = None


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
    modality = raw.get("modality")
    if modality is not None and modality not in get_args(Modality):
        raise ValueError("modality precisa ser transcription, writing ou conversation.")
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
        modality=modality,
    )


async def _conversation_metrics(session: AsyncSession, provider_name: str) -> GateMetrics:
    # Um turno contém texto e STT: somar o job novamente duplicaria o custo.
    successful = (
        (DialogueTurn.state == "completed")
        & ~DialogueTurn.fallback
        & DialogueTurn.error_code.is_(None)
    )
    terminal = DialogueTurn.state.in_(("completed", "failed"))
    rated = successful & DialogueTurn.human_rating.is_not(None)
    row = (
        await session.execute(
            select(
                func.count(DialogueTurn.id),
                func.count(DialogueTurn.id).filter(successful),
                func.count(DialogueTurn.id).filter(terminal & ~successful),
                func.count(DialogueTurn.id).filter(rated),
                func.count(DialogueTurn.id).filter(
                    successful, DialogueTurn.human_rating == "helpful"
                ),
                func.coalesce(func.sum(DialogueTurn.cost_microusd), 0),
                func.count(func.distinct(SpeakingDialogue.lesson_id)).filter(rated),
                func.count(DialogueTurn.id).filter(
                    terminal, AssistReservation.cost_known.is_distinct_from(True)
                ),
            )
            .select_from(DialogueTurn)
            .join(SpeakingDialogue, DialogueTurn.dialogue_id == SpeakingDialogue.id)
            .outerjoin(TranscriptionJob, DialogueTurn.transcription_job_id == TranscriptionJob.id)
            .outerjoin(
                AssistReservation,
                TranscriptionJob.assist_reservation_id == AssistReservation.id,
            )
            .where(
                SpeakingDialogue.mode == "guided",
                SpeakingDialogue.provider_name == provider_name,
                DialogueTurn.role == "student",
                DialogueTurn.user_id == SpeakingDialogue.user_id,
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
        rated_lessons=int(row[6]),
        unknown_cost_turns=int(row[7]),
    )


async def collect_gate_metrics(
    session: AsyncSession, modality: Modality, *, provider_name: str | None = None
) -> GateMetrics:
    if modality == "conversation":
        if not provider_name or not provider_name.strip():
            raise ValueError("conversation exige o nome do provedor avaliado.")
        return await _conversation_metrics(session, provider_name)
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
                ).where(TranscriptionJob.kind == "transcription")
            )
        ).one()
    elif modality == "writing":
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
    else:
        raise ValueError("Modalidade de assistência inválida.")

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
    providers: dict[Modality, bool] = {
        "transcription": bool(settings.assist_transcription_url),
        "writing": settings.writing_assist_configured,
        "conversation": settings.dialogue_assist_configured,
    }
    provider_configured = providers[modality]
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
        # Arredondamento é só para exibição, nunca para decidir o limiar.
        "helpful_rate": metrics.rated > 0 and metrics.helpful * 5 >= metrics.rated * 4,
        "technical_failure_rate": metrics.successful + metrics.failed > 0
        and metrics.failed * 20 < metrics.successful + metrics.failed,
        "safety_review_approved": review.safety_review_approved,
        "automation_notice_understood": review.automation_notice_understood,
    }
    if review.modality is not None or modality == "conversation":
        criteria["review_modality_matches"] = review.modality == modality
    if modality == "conversation":
        criteria["minimum_rated_lessons"] = metrics.rated_lessons >= 5
        criteria["cost_known"] = metrics.unknown_cost_turns == 0
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
