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


class OperationsMetricsOut(BaseModel):
    sampled_at: datetime
    requests: RequestMetricsOut
    database: DatabaseMetricsOut
    transcription_queue: QueueMetricsOut
    account_deletions: DeletionMetricsOut
    legacy_review: LegacyReviewMetricsOut
    media: MediaMetricsOut
