"""Sondas da telemetria operacional.

Cada sonda é uma consulta agregada de cardinalidade fixa: contagens, tamanhos e
marcas de tempo. Nada aqui lê texto de aluno, e-mail, token ou áudio, e nenhuma
sonda devolve linha por usuário — o que sai daqui pode ir para um painel sem
virar vazamento.
"""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple, cast

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import AssistReservation
from app.db.session import get_engine
from app.observability import request_metrics
from app.schemas.operations import (
    AssistCostsOut,
    AssistCostWindowOut,
    DatabaseMetricsOut,
    DeletionMetricsOut,
    DialogueMetricsOut,
    LegacyReviewMetricsOut,
    MediaMetricsOut,
    OperationsMetricsOut,
    QueueMetricsOut,
    RelationMetricsOut,
    RequestMetricsOut,
)
from app.services.assist_quota import DIALOGUE_MODALITY, daily_limit


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


class DialogueRow(NamedTuple):
    turns: int
    completed: int
    failed: int
    fallback: int
    provider_failures: int
    latency_p95_ms: int | None
    cost_microusd: int


async def _dialogue(session: AsyncSession) -> DialogueRow:
    """Turnos do aluno no dia UTC corrente.

    Só turnos do aluno entram em `turns`: a resposta do parceiro vive na mesma
    linha, e contar as duas pontas dobraria o número que o painel compara com a
    cota. O p95 é da latência do turno — do que o aluno enviou até o resultado
    ficar pronto —, que é a medida que o ADR fixou em 8 segundos.
    """
    row = (
        await session.execute(
            text(
                """
                WITH hoje AS (
                    SELECT * FROM public.dialogue_turn
                    WHERE role = 'student'
                      AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')
                )
                SELECT count(*),
                       count(*) FILTER (WHERE state = 'completed'),
                       count(*) FILTER (WHERE state = 'failed'),
                       count(*) FILTER (WHERE fallback),
                       count(*) FILTER (WHERE error_code IS NOT NULL),
                       percentile_cont(0.95) WITHIN GROUP (
                           ORDER BY extract(epoch FROM completed_at - created_at)
                       ) FILTER (WHERE completed_at IS NOT NULL),
                       coalesce(sum(cost_microusd), 0)
                FROM hoje
                """
            )
        )
    ).one()
    p95 = row[5]
    return DialogueRow(
        turns=int(row[0]),
        completed=int(row[1]),
        failed=int(row[2]),
        fallback=int(row[3]),
        provider_failures=int(row[4]),
        latency_p95_ms=max(0, round(float(p95) * 1000)) if p95 is not None else None,
        cost_microusd=int(row[6]),
    )


async def _dialogue_quota(session: AsyncSession, limit: int) -> tuple[int, int]:
    """Consumo da cota de conversa e quantas contas bateram no teto.

    A definição de "usado" é a mesma de `assist_quota.usage` — reservado ainda
    válido mais consumido, no dia UTC. Duas definições de consumo divergiriam
    na primeira mudança de regra, e o painel passaria a discordar do 429 que o
    aluno recebeu.
    """
    row = (
        await session.execute(
            text(
                """
                WITH por_conta AS (
                    SELECT user_id,
                           count(*) FILTER (
                               WHERE state = 'reserved' AND expires_at > now()
                           ) + count(*) FILTER (WHERE state = 'consumed') AS usado
                    FROM public.assist_reservation
                    WHERE modality = :modality
                      AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')
                    GROUP BY user_id
                )
                SELECT coalesce(sum(usado), 0),
                       count(*) FILTER (WHERE usado >= :limit)
                FROM por_conta
                """
            ),
            {"modality": DIALOGUE_MODALITY, "limit": limit},
        )
    ).one()
    return int(row[0]), int(row[1])


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


async def _assist_costs(session: AsyncSession, now: datetime) -> AssistCostsOut:
    now = now.astimezone(UTC)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    next_month = (month + timedelta(days=32)).replace(day=1)
    # Ledger sobrevive à exclusão do turno/job. Legados sem dispatched_at
    # usam created_at; nunca contamos reserva apenas criada ou liberada.
    dispatched = func.coalesce(AssistReservation.dispatched_at, AssistReservation.created_at)
    today = dispatched >= day
    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(AssistReservation.cost_microusd), 0),
                func.count().filter(~AssistReservation.cost_known),
                func.count().filter(today),
                func.coalesce(func.sum(AssistReservation.cost_microusd).filter(today), 0),
                func.count().filter(today, ~AssistReservation.cost_known),
            ).where(
                AssistReservation.state == "consumed",
                AssistReservation.modality.in_(("transcription", "writing", "conversation")),
                dispatched >= month,
                dispatched <= now,
            )
        )
    ).one()
    return AssistCostsOut(
        daily=AssistCostWindowOut(
            starts_at=day,
            ends_at=day + timedelta(days=1),
            consumed=int(row[3]),
            cost_microusd=int(row[4]),
            unknown_cost_reservations=int(row[5]),
        ),
        monthly=AssistCostWindowOut(
            starts_at=month,
            ends_at=next_month,
            consumed=int(row[0]),
            cost_microusd=int(row[1]),
            unknown_cost_reservations=int(row[2]),
        ),
    )


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
    dialogue = await _dialogue(session)
    assist_costs = await _assist_costs(session, now)
    quota_limit = daily_limit(DIALOGUE_MODALITY)
    quota_used, quota_exhausted = await _dialogue_quota(session, quota_limit)
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
        dialogue=DialogueMetricsOut(
            turns=dialogue.turns,
            completed=dialogue.completed,
            failed=dialogue.failed,
            fallback=dialogue.fallback,
            provider_failures=dialogue.provider_failures,
            latency_p95_ms=dialogue.latency_p95_ms,
            cost_microusd=dialogue.cost_microusd,
            quota_limit=quota_limit,
            quota_used=quota_used,
            quota_exhausted_accounts=quota_exhausted,
        ),
        account_deletions=DeletionMetricsOut(pending=deletions[0], failed=deletions[1]),
        assist_costs=assist_costs,
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
