"""Modelos da telemetria operacional.

Cardinalidade fixa por construção: nenhum campo aqui carrega texto de aluno,
e-mail, token ou áudio — só contagens, tamanhos e marcas de tempo.
"""

from datetime import datetime

from pydantic import BaseModel


class RequestMetricsOut(BaseModel):
    scope: str = "process"
    process_uptime_seconds: int
    requests_total: int
    responses_5xx_total: int
    duration_ms_sum: float
    duration_ms_max: float
    latency_buckets_ms: dict[str, int]


class DatabaseMetricsOut(BaseModel):
    size_bytes: int
    public_relations_bytes: int
    connections: int
    waiting_locks: int
    pool_size: int | None
    pool_checked_out: int | None
    pool_overflow: int | None
    largest_relations: list["RelationMetricsOut"]


class RelationMetricsOut(BaseModel):
    relation: str
    total_bytes: int


class QueueMetricsOut(BaseModel):
    queued: int
    processing: int
    failed: int
    retry_events: int
    expired: int
    oldest_queued_seconds: int | None
    worker_seen_at: datetime | None
    worker_age_seconds: int | None
    maintenance_at: datetime | None
    maintenance_age_seconds: int | None
    maintenance_counts: dict[str, int] | None


class DeletionMetricsOut(BaseModel):
    pending: int
    failed: int


class LegacyReviewMetricsOut(BaseModel):
    cards: int
    unlinked_cards: int
    mismatched_links: int


class MediaMetricsOut(BaseModel):
    referenced_files: int
    referenced_bytes: int
    filesystem_available: bool
    filesystem_capacity_bytes: int | None
    filesystem_free_bytes: int | None


class DialogueMetricsOut(BaseModel):
    """Conversa do dia em números (INFRA-46).

    Nenhum campo carrega texto: o painel precisa saber quanto rodou, quanto
    demorou, quanto falhou e quanto custou — nunca o que o aluno disse. O
    recorte é o dia UTC, o mesmo da cota, para que `quota_used` e `turns`
    possam ser comparados sem ajuste de relógio.
    """

    turns: int
    completed: int
    failed: int
    # Turno que veio do roteiro da aula porque o provedor não serviu. Não é
    # falha de requisição: o aluno foi atendido, só não pelo modelo.
    fallback: int
    provider_failures: int
    latency_p95_ms: int | None
    cost_microusd: int
    quota_limit: int
    quota_used: int
    # Quantas contas bateram no teto hoje, sem dizer quais.
    quota_exhausted_accounts: int


class AssistCostWindowOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    consumed: int
    cost_microusd: int
    unknown_cost_reservations: int


class AssistCostsOut(BaseModel):
    """Ledger existente das três modalidades, por despacho e calendário UTC."""

    daily: AssistCostWindowOut
    monthly: AssistCostWindowOut


class OperationsMetricsOut(BaseModel):
    sampled_at: datetime
    requests: RequestMetricsOut
    database: DatabaseMetricsOut
    transcription_queue: QueueMetricsOut
    dialogue: DialogueMetricsOut
    assist_costs: AssistCostsOut
    account_deletions: DeletionMetricsOut
    legacy_review: LegacyReviewMetricsOut
    media: MediaMetricsOut
