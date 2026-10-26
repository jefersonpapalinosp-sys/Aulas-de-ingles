"""Sondas da telemetria operacional.

Cada sonda é uma consulta agregada de cardinalidade fixa: contagens, tamanhos e
marcas de tempo. Nada aqui lê texto de aluno, e-mail, token ou áudio, e nenhuma
sonda devolve linha por usuário — o que sai daqui pode ir para um painel sem
virar vazamento.
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_engine
from app.observability import request_metrics
from app.schemas.operations import (
    DatabaseMetricsOut,
    DeletionMetricsOut,
    LegacyReviewMetricsOut,
    MediaMetricsOut,
    OperationsMetricsOut,
    QueueMetricsOut,
    RelationMetricsOut,
    RequestMetricsOut,
)


class QueueRow(NamedTuple):
    queued: int
    processing: int
    failed: int
    retry_events: int
    expired: int
    oldest_queued_seconds: int | None


class Heartbeat(NamedTuple):
    seen_at: datetime | None
    maintenance_at: datetime | None
    counts: dict[str, int] | None


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


async def _database(session: AsyncSession) -> tuple[int, int, int, int]:
    row = (
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
    return int(row[0]), int(row[1]), int(row[2]), int(row[3])


async def _largest_relations(session: AsyncSession) -> list[RelationMetricsOut]:
    rows = (
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
    return [RelationMetricsOut(relation=str(name), total_bytes=int(size)) for name, size in rows]


async def _queue(session: AsyncSession) -> QueueRow:
    row = (
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
    return QueueRow(
        queued=int(row[0]),
        processing=int(row[1]),
        failed=int(row[2]),
        retry_events=int(row[3]),
        expired=int(row[4]),
        oldest_queued_seconds=max(0, int(row[5])) if row[5] is not None else None,
    )


async def _heartbeat(session: AsyncSession) -> Heartbeat | None:
    row = (
        await session.execute(
            text(
                "SELECT seen_at, maintenance_at, maintenance_counts "
                "FROM worker_heartbeat WHERE name='transcription'"
            )
        )
    ).one_or_none()
    if row is None:
        return None
    return Heartbeat(
        seen_at=row[0],
        maintenance_at=row[1],
        counts=cast(dict[str, int] | None, row[2]),
    )


async def _deletions(session: AsyncSession) -> tuple[int, int]:
    row = (
        await session.execute(
            text(
                "SELECT count(*) FILTER (WHERE state='cleanup_pending'), "
                "count(*) FILTER (WHERE state='failed') FROM account_deletion_job"
            )
        )
    ).one()
    return int(row[0]), int(row[1])


async def _legacy_review(session: AsyncSession) -> tuple[int, int, int]:
    """``review_card`` permanece durante a linha de exportação 2.x; o painel
    acompanha cartões sem ``review_item`` e vínculos divergentes."""
    row = (
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
    return int(row[0]), int(row[1]), int(row[2])


async def _media(session: AsyncSession) -> tuple[int, int]:
    row = (
        await session.execute(
            text(
                "SELECT count(*) FILTER (WHERE storage_key IS NOT NULL), "
                "coalesce(sum(file_size) FILTER (WHERE storage_key IS NOT NULL), 0) "
                "FROM speaking_attempt"
            )
        )
    ).one()
    return int(row[0]), int(row[1])


def _queue_out(queue: QueueRow, heartbeat: Heartbeat | None, now: datetime) -> QueueMetricsOut:
    """Idade do worker e da manutenção são derivadas aqui: o painel compara
    com o limiar de alerta sem precisar saber o relógio do processo."""
    seen = heartbeat.seen_at if heartbeat else None
    maintenance = heartbeat.maintenance_at if heartbeat else None
    return QueueMetricsOut(
        queued=queue.queued,
        processing=queue.processing,
        failed=queue.failed,
        retry_events=queue.retry_events,
        expired=queue.expired,
        oldest_queued_seconds=queue.oldest_queued_seconds,
        worker_seen_at=seen,
        worker_age_seconds=(max(0, int((now - seen).total_seconds())) if seen else None),
        maintenance_at=maintenance,
        maintenance_age_seconds=(
            max(0, int((now - maintenance).total_seconds())) if maintenance else None
        ),
        maintenance_counts=heartbeat.counts if heartbeat else None,
    )


async def snapshot(session: AsyncSession, settings: Settings) -> OperationsMetricsOut:
    """Uma amostra completa, com todas as sondas lidas na mesma sessão."""
    now = datetime.now(UTC)
    database = await _database(session)
    largest_relations = await _largest_relations(session)
    queue = await _queue(session)
    heartbeat = await _heartbeat(session)
    deletions = await _deletions(session)
    legacy_review = await _legacy_review(session)
    media = await _media(session)
    request = request_metrics.snapshot()
    filesystem_available, filesystem_capacity, filesystem_free = _disk_metrics(
        settings.speaking_storage_dir
    )
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
            size_bytes=database[0],
            public_relations_bytes=database[1],
            connections=database[2],
            waiting_locks=database[3],
            pool_size=_pool_value("size"),
            pool_checked_out=_pool_value("checkedout"),
            pool_overflow=_pool_value("overflow"),
            largest_relations=largest_relations,
        ),
        transcription_queue=_queue_out(queue, heartbeat, now),
        account_deletions=DeletionMetricsOut(pending=deletions[0], failed=deletions[1]),
        legacy_review=LegacyReviewMetricsOut(
            cards=legacy_review[0],
            unlinked_cards=legacy_review[1],
            mismatched_links=legacy_review[2],
        ),
        media=MediaMetricsOut(
            referenced_files=media[0],
            referenced_bytes=media[1],
            filesystem_available=filesystem_available,
            filesystem_capacity_bytes=filesystem_capacity,
            filesystem_free_bytes=filesystem_free,
        ),
    )
