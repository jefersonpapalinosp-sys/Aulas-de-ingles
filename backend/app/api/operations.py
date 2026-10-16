"""Telemetria operacional agregada e protegida, sem dados de alunos."""

import hmac
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_engine, get_session
from app.observability import request_metrics

router = APIRouter(prefix="/operations", tags=["operations"])
bearer = HTTPBearer(auto_error=False)


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


def _authorized(
    credentials: HTTPAuthorizationCredentials | None,
    settings: Settings,
) -> None:
    configured = settings.operations_token
    if not configured:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Não encontrado.")
    supplied = (
        credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    )
    if not hmac.compare_digest(supplied, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial operacional inválida.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _pool_value(name: str) -> int | None:
    method = getattr(get_engine().sync_engine.pool, name, None)
    value = method() if callable(method) else None
    return int(value) if isinstance(value, int) else None


def _disk_metrics(path: str) -> tuple[bool, int | None, int | None]:
    try:
        usage = shutil.disk_usage(Path(path))
    except OSError:
        return False, None, None
    return True, usage.total, usage.free


@router.get("/metrics", response_model=OperationsMetricsOut)
async def metrics(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OperationsMetricsOut:
    """Snapshot de cardinalidade fixa; nunca retorna texto, e-mail, token ou áudio."""
    _authorized(credentials, settings)
    now = datetime.now(UTC)
    database = (
        await session.execute(
            text(
                """
                SELECT pg_database_size(current_database()),
                       coalesce((SELECT sum(pg_total_relation_size(c.oid))
                                 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                                 WHERE n.nspname='public' AND c.relkind IN ('r','m')), 0),
                       (SELECT count(*) FROM pg_stat_activity
                        WHERE datname=current_database()),
                       (SELECT count(*) FROM pg_locks WHERE NOT granted)
                """
            )
        )
    ).one()
    largest_relations = (
        await session.execute(
            text(
                """
                SELECT c.relname, pg_total_relation_size(c.oid)
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind IN ('r','m')
                ORDER BY pg_total_relation_size(c.oid) DESC, c.relname
                LIMIT 5
                """
            )
        )
    ).all()
    queue = (
        await session.execute(
            text(
                """
                SELECT count(*) FILTER (WHERE status='queued' AND expires_at>now()),
                       count(*) FILTER (WHERE status='processing' AND expires_at>now()),
                       count(*) FILTER (WHERE status='failed'),
                       coalesce(sum(greatest(attempt_count-1, 0)), 0),
                       count(*) FILTER (WHERE expires_at<=now() OR error_code='job_expired'),
                       extract(epoch FROM now()-min(requested_at)
                               FILTER (WHERE status='queued' AND expires_at>now()))
                FROM transcription_job
                """
            )
        )
    ).one()
    heartbeat = (
        await session.execute(
            text(
                "SELECT seen_at, maintenance_at, maintenance_counts "
                "FROM worker_heartbeat WHERE name='transcription'"
            )
        )
    ).one_or_none()
    deletions = (
        await session.execute(
            text(
                "SELECT count(*) FILTER (WHERE state='cleanup_pending'), "
                "count(*) FILTER (WHERE state='failed') FROM account_deletion_job"
            )
        )
    ).one()
    legacy_review = (
        await session.execute(
            text(
                """
                SELECT count(c.id),
                       count(c.id) FILTER (WHERE i.id IS NULL),
                       count(c.id) FILTER (
                         WHERE i.id IS NOT NULL AND
                           (i.user_id<>c.user_id OR i.vocab_item_id<>c.vocab_item_id))
                FROM review_card c
                LEFT JOIN review_item i ON i.legacy_card_id=c.id
                """
            )
        )
    ).one()
    media = (
        await session.execute(
            text(
                "SELECT count(*) FILTER (WHERE storage_key IS NOT NULL), "
                "coalesce(sum(file_size) FILTER (WHERE storage_key IS NOT NULL), 0) "
                "FROM speaking_attempt"
            )
        )
    ).one()
    request = request_metrics.snapshot()
    filesystem_available, filesystem_capacity, filesystem_free = _disk_metrics(
        settings.speaking_storage_dir
    )
    worker_seen = heartbeat[0] if heartbeat else None
    return OperationsMetricsOut(
        sampled_at=now,
        requests=RequestMetricsOut(
            process_uptime_seconds=request.process_uptime_seconds,
            requests_total=request.requests_total,
            responses_5xx_total=request.responses_5xx_total,
            duration_ms_sum=request.duration_ms_sum,
            duration_ms_max=request.duration_ms_max,
            latency_buckets_ms=request.latency_buckets,
        ),
        database=DatabaseMetricsOut(
            size_bytes=int(database[0]),
            public_relations_bytes=int(database[1]),
            connections=int(database[2]),
            waiting_locks=int(database[3]),
            pool_size=_pool_value("size"),
            pool_checked_out=_pool_value("checkedout"),
            pool_overflow=_pool_value("overflow"),
            largest_relations=[
                RelationMetricsOut(relation=str(name), total_bytes=int(size))
                for name, size in largest_relations
            ],
        ),
        transcription_queue=QueueMetricsOut(
            queued=int(queue[0]),
            processing=int(queue[1]),
            failed=int(queue[2]),
            retry_events=int(queue[3]),
            expired=int(queue[4]),
            oldest_queued_seconds=max(0, int(queue[5])) if queue[5] is not None else None,
            worker_seen_at=worker_seen,
            worker_age_seconds=(
                max(0, int((now - worker_seen).total_seconds())) if worker_seen else None
            ),
            maintenance_at=heartbeat[1] if heartbeat else None,
            maintenance_age_seconds=(
                max(0, int((now - heartbeat[1]).total_seconds()))
                if heartbeat and heartbeat[1]
                else None
            ),
            maintenance_counts=heartbeat[2] if heartbeat else None,
        ),
        account_deletions=DeletionMetricsOut(pending=int(deletions[0]), failed=int(deletions[1])),
        legacy_review=LegacyReviewMetricsOut(
            cards=int(legacy_review[0]),
            unlinked_cards=int(legacy_review[1]),
            mismatched_links=int(legacy_review[2]),
        ),
        media=MediaMetricsOut(
            referenced_files=int(media[0]),
            referenced_bytes=int(media[1]),
            filesystem_available=filesystem_available,
            filesystem_capacity_bytes=filesystem_capacity,
            filesystem_free_bytes=filesystem_free,
        ),
    )
