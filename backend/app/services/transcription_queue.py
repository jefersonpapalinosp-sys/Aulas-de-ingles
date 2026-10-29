"""Fila durável de transcrição apoiada pelo PostgreSQL.

A API apenas persiste jobs. Um processo worker separado reivindica uma linha
com ``FOR UPDATE SKIP LOCKED``, chama o gateway fora da transação e grava o
resultado somente se ainda possuir aquela tentativa. Isso permite vários
workers, retomada após reinício e retry sem duplicar a requisição lógica.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, true, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import DialogueTurn, SpeakingAttempt, SpeakingDialogue, TranscriptionJob
from app.db.session import dispose_engine, get_sessionmaker
from app.domain.enums import JobKind
from app.services import (
    account_deletion,
    assist_quota,
    assistance,
    cloudflare_provider,
    editorial_history,
    maintenance,
)
from app.services import dialogue as dialogue_service
from app.services.audio_storage import AudioStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedJob:
    job_id: int
    attempt_number: int
    reservation_id: int | None = None
    # A fila passou a ter dois tipos no BE-46; quem reivindica precisa saber
    # qual, porque o despacho é outro.
    kind: JobKind = "transcription"


async def _recover_stale_jobs(now: datetime) -> None:
    settings = get_settings()
    cutoff = now - timedelta(seconds=settings.assist_job_stale_seconds)
    async with get_sessionmaker()() as session, session.begin():
        retryable = (
            (TranscriptionJob.status == "processing")
            & (TranscriptionJob.processing_started_at <= cutoff)
            & (TranscriptionJob.attempt_count < TranscriptionJob.max_attempts)
            & (TranscriptionJob.expires_at > now)
        )
        retry_ids = (
            select(TranscriptionJob.id)
            .where(retryable)
            .order_by(TranscriptionJob.id)
            .limit(settings.maintenance_batch_size)
            .with_for_update(skip_locked=True)
        )
        await session.execute(
            update(TranscriptionJob)
            .where(TranscriptionJob.id.in_(retry_ids))
            .values(
                status="queued",
                error_code="worker_interrupted",
                next_attempt_at=now,
                processing_started_at=None,
            )
        )
        exhausted = (
            (TranscriptionJob.status == "queued")
            | (
                (TranscriptionJob.status == "processing")
                & (TranscriptionJob.processing_started_at <= cutoff)
            )
        ) & (TranscriptionJob.attempt_count >= TranscriptionJob.max_attempts)
        exhausted_ids = (
            select(TranscriptionJob.id)
            .where(exhausted, TranscriptionJob.expires_at > now)
            .order_by(TranscriptionJob.id)
            .limit(settings.maintenance_batch_size)
            .with_for_update(skip_locked=True)
        )
        await session.execute(
            update(TranscriptionJob)
            .where(TranscriptionJob.id.in_(exhausted_ids))
            .values(
                status="failed",
                error_code="attempts_exhausted",
                processing_started_at=None,
                completed_at=now,
            )
        )


async def _claim_next_job(now: datetime) -> ClaimedJob | None:
    await _recover_stale_jobs(now)
    settings = get_settings()
    account_filter = (
        TranscriptionJob.user_id.in_(settings.dialogue_pilot_user_ids)
        if settings.assist_accounts_restricted
        else true()
    )
    claim: ClaimedJob | None = None
    async with get_sessionmaker()() as session, session.begin():
        job = (
            await session.execute(
                select(TranscriptionJob)
                .where(
                    account_filter,
                    TranscriptionJob.status == "queued",
                    TranscriptionJob.next_attempt_at <= now,
                    TranscriptionJob.attempt_count < TranscriptionJob.max_attempts,
                    TranscriptionJob.expires_at > now,
                )
                .order_by(TranscriptionJob.next_attempt_at, TranscriptionJob.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if job is None:
            return None
        job.status = "processing"
        job.attempt_count += 1
        job.processing_started_at = now
        job.error_code = None
        claim = ClaimedJob(job.id, job.attempt_count, job.assist_reservation_id, job.kind)
    assert claim is not None
    logger.info(
        "transcription_claimed",
        extra={"job_id": claim.job_id, "attempt": claim.attempt_number},
    )
    return claim


async def _authorize_dispatch(claim: ClaimedJob) -> bool:
    async with get_sessionmaker()() as session, session.begin():
        job = (
            await session.execute(
                select(TranscriptionJob)
                .where(
                    TranscriptionJob.id == claim.job_id,
                    TranscriptionJob.status == "processing",
                    TranscriptionJob.attempt_count == claim.attempt_number,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if job is None:
            return False
        error_code = "reservation_unavailable"
        if not get_settings().assist_account_allowed(job.user_id):
            error_code = "assist_disabled"
            await assist_quota.release(session, job.assist_reservation_id, error_code)
            allowed = False
        elif job.expires_at <= datetime.now(UTC):
            await assist_quota.release(session, job.assist_reservation_id, "job_expired")
            allowed = False
        else:
            allowed = await assist_quota.consume(session, job.assist_reservation_id)
        if not allowed:
            job.status, job.error_code = "failed", error_code
            job.processing_started_at = None
            job.completed_at = datetime.now(UTC)
        return allowed


async def _record_failure(claim: ClaimedJob, code: str, *, retryable: bool) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session, session.begin():
        job = (
            await session.execute(
                select(TranscriptionJob)
                .where(
                    TranscriptionJob.id == claim.job_id,
                    TranscriptionJob.status == "processing",
                    TranscriptionJob.attempt_count == claim.attempt_number,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if job is None:
            return
        if retryable and job.attempt_count < job.max_attempts and job.expires_at > now:
            delay = settings.assist_job_retry_base_seconds * (2 ** (job.attempt_count - 1))
            job.status = "queued"
            job.next_attempt_at = now + timedelta(seconds=delay)
            job.completed_at = None
        else:
            job.status = "failed"
            job.completed_at = now
            await assist_quota.release(session, job.assist_reservation_id, code)
        job.error_code = code
        job.processing_started_at = None
    logger.warning(
        "transcription_failed",
        extra={
            "job_id": claim.job_id,
            "attempt": claim.attempt_number,
            "error_code": code,
            "retryable": retryable,
        },
    )


async def _record_success(
    claim: ClaimedJob,
    result: assistance.TranscriptionResult,
    expected_text: str,
) -> None:
    async with get_sessionmaker()() as session, session.begin():
        job = (
            await session.execute(
                select(TranscriptionJob)
                .where(
                    TranscriptionJob.id == claim.job_id,
                    TranscriptionJob.status == "processing",
                    TranscriptionJob.attempt_count == claim.attempt_number,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        # O custo confirmado permanece mesmo se o usuário apagou o resultado
        # durante o processamento. Não recria job nem transcrição apagados.
        if result.cost_known:
            await assist_quota.record_cost(session, claim.reservation_id, result.cost_microusd)
        if job is None:
            return
        if job.expires_at <= datetime.now(UTC):
            job.status, job.error_code = "failed", "job_expired"
            job.processing_started_at = None
            job.completed_at = datetime.now(UTC)
            return
        job.status = "completed"
        job.transcript_text = result.text
        job.words = result.words
        job.mean_confidence = result.mean_confidence
        job.similarity_score = assistance.compare_transcript(expected_text, result.text)
        job.low_confidence = result.mean_confidence is None or result.mean_confidence < 0.75
        job.cost_microusd = result.cost_microusd
        job.error_code = None
        job.processing_started_at = None
        job.completed_at = datetime.now(UTC)
    logger.info(
        "transcription_completed",
        extra={"job_id": claim.job_id, "attempt": claim.attempt_number},
    )


async def _dialogue_transcript(
    session: AsyncSession, settings: Settings, turn: DialogueTurn
) -> tuple[str | None, str | None, assistance.TranscriptionResult | None]:
    """Transcrição do turno: já vem pronta no texto, ou sai do áudio.

    Devolve `(transcript, erro, metadados de STT)`. O turno por texto não gasta STT — é por isso
    que entrar por texto é alternativa de primeira classe e não um degrau
    inferior: custa menos e falha menos.
    """
    if turn.input_kind == "text":
        return (turn.transcript or ""), None, None
    attempt = (
        await session.execute(
            select(SpeakingAttempt).where(SpeakingAttempt.id == turn.speaking_attempt_id)
        )
    ).scalar_one_or_none()
    if attempt is None or not attempt.storage_key or not attempt.mime_type:
        return None, "audio_unavailable", None
    if not settings.assist_transcription_url:
        return None, "feature_disabled", None
    storage = AudioStorage(settings.speaking_storage_dir)
    try:
        audio = await asyncio.to_thread(
            storage.read_verified,
            attempt.storage_key,
            attempt.audio_sha256,
            settings.speaking_max_bytes,
        )
    except (OSError, ValueError):
        return None, "audio_unavailable", None
    try:
        result = await asyncio.to_thread(
            cloudflare_provider.transcribe
            if settings.assist_provider_kind == "cloudflare"
            else assistance.call_transcription_provider,
            settings.assist_transcription_url,
            audio,
            attempt.mime_type,
            token=settings.assist_provider_token,
            timeout=settings.assist_timeout_seconds,
            idempotency_key=f"dialogue-stt-{turn.id}",
        )
    except assistance.ProviderFailure as error:
        return None, error.code, None
    except Exception:
        return None, "internal_provider_error", None
    return result.text, None, result


async def _process_dialogue_claim(claim: ClaimedJob) -> bool:
    """Fecha um turno de diálogo reivindicado.

    A ordem repete a da transcrição: carregar o necessário, autorizar o
    despacho (que é onde a cota é consumida), e só então falar com fora. Falha
    de provedor não falha o job — `resolve_turn` grava o turno com o roteiro e
    `fallback=true`, porque o aluno precisa poder continuar a conversa.
    """
    settings = get_settings()
    async with get_sessionmaker()() as session:
        turn = (
            await session.execute(
                select(DialogueTurn).where(DialogueTurn.transcription_job_id == claim.job_id)
            )
        ).scalar_one_or_none()
        if turn is None:
            await _record_failure(claim, "dialogue_turn_missing", retryable=False)
            return True
        dialogue_row = (
            await session.execute(
                select(SpeakingDialogue).where(SpeakingDialogue.id == turn.dialogue_id)
            )
        ).scalar_one()
        lesson = await dialogue_service.lesson_for_dialogue(session, dialogue_row.lesson_id)
        if not await _authorize_dispatch(claim):
            return True
        transcript, erro, stt = await _dialogue_transcript(session, settings, turn)
        if transcript is None:
            await _record_failure(claim, erro or "internal_provider_error", retryable=False)
            return True
        brief = await dialogue_service.brief_for_lesson(session, lesson)
        outcome = await dialogue_service.resolve_turn(
            session, turn, dialogue_row, brief, transcript
        )
        # Resultado, custo e confirmação do job são atômicos. Uma queda
        # entre commits não pode deixar o turno pronto com custo não registrado.
        total_cost = outcome.cost_microusd + (stt.cost_microusd if stt else 0)
        cost_known = outcome.cost_known and (stt.cost_known if stt else True)
        if stt is not None:
            turn.cost_microusd = total_cost
            await assist_quota.record_cost(
                session, claim.reservation_id, total_cost, known=cost_known
            )
        elif outcome.cost_known:
            await assist_quota.record_cost(session, claim.reservation_id, outcome.cost_microusd)
        job = (
            await session.execute(
                select(TranscriptionJob).where(TranscriptionJob.id == claim.job_id)
            )
        ).scalar_one_or_none()
        if job is not None:
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            job.processing_started_at = None
            job.error_code = outcome.error_code
            if stt is not None:
                job.words = stt.words
                job.transcript_text = stt.text
                job.mean_confidence = stt.mean_confidence
                job.cost_microusd = total_cost
        await session.commit()
    logger.info(
        "dialogue_job_completed",
        extra={
            "job_id": claim.job_id,
            "fallback": outcome.fallback,
            "error_code": outcome.error_code,
        },
    )
    return True


async def process_next_transcription() -> bool:
    """Processa no máximo um job; retorna se algum registro foi reivindicado."""

    settings = get_settings()
    # O worker atende dois tipos de job com provedores diferentes: exigir a URL
    # de transcrição para tudo deixaria o diálogo parado na fila quando só a
    # transcrição estivesse desconfigurada.
    if not settings.assisted_features_enabled:
        return False
    if not settings.assist_transcription_url and not settings.dialogue_assist_configured:
        return False
    claim = await _claim_next_job(datetime.now(UTC))
    if claim is None:
        return False
    if claim.kind == "dialogue":
        return await _process_dialogue_claim(claim)
    if not settings.assist_transcription_url:
        await _record_failure(claim, "feature_disabled", retryable=False)
        return True

    async with get_sessionmaker()() as session:
        job = (
            await session.execute(
                select(TranscriptionJob).where(TranscriptionJob.id == claim.job_id)
            )
        ).scalar_one_or_none()
        if job is None:
            return True
        attempt = (
            await session.execute(
                select(SpeakingAttempt).where(SpeakingAttempt.id == job.speaking_attempt_id)
            )
        ).scalar_one_or_none()
        if attempt is None or not attempt.storage_key or not attempt.mime_type:
            await _record_failure(claim, "audio_unavailable", retryable=False)
            return True
        idempotency_key = job.idempotency_key
        expected_text = await editorial_history.worker_speaking_expected_text(
            session, attempt.id, job.user_id
        )
        mime_type = attempt.mime_type
        path = AudioStorage(settings.speaking_storage_dir).path(attempt.storage_key)

    if expected_text is None:
        await _record_failure(claim, "historical_content_unavailable", retryable=False)
        return True
    if path is None:
        await _record_failure(claim, "audio_unavailable", retryable=False)
        return True
    try:
        audio = await asyncio.to_thread(
            AudioStorage(settings.speaking_storage_dir).read_verified,
            attempt.storage_key,
            attempt.audio_sha256,
            settings.speaking_max_bytes,
        )
    except (OSError, ValueError):
        await _record_failure(claim, "audio_unavailable", retryable=False)
        return True
    if not await _authorize_dispatch(claim):
        return True
    try:
        result = await asyncio.to_thread(
            cloudflare_provider.transcribe
            if settings.assist_provider_kind == "cloudflare"
            else assistance.call_transcription_provider,
            settings.assist_transcription_url,
            audio,
            mime_type,
            token=settings.assist_provider_token,
            timeout=settings.assist_timeout_seconds,
            idempotency_key=idempotency_key,
        )
    except assistance.ProviderFailure as error:
        await _record_failure(claim, error.code, retryable=True)
    except Exception:
        # Conteúdo, áudio e exceção do fornecedor não entram nos logs.
        await _record_failure(claim, "internal_provider_error", retryable=True)
    else:
        await _record_success(claim, result, expected_text)
    return True


async def run_transcription_worker(*, once: bool = False) -> None:
    """Executa o consumidor contínuo ou uma única iteração operacional."""

    settings = get_settings()
    failures = 0
    last_maintenance = float("-inf")
    last_heartbeat = float("-inf")
    try:
        while True:
            try:
                now = time.monotonic()
                if now - last_maintenance >= settings.maintenance_interval_seconds:
                    counts = await maintenance.sweep()
                    await maintenance.heartbeat(counts)
                    logger.info(
                        "maintenance_batch",
                        extra={"counts": counts, "limit": settings.maintenance_batch_size},
                    )
                    last_maintenance = last_heartbeat = now
                elif now - last_heartbeat >= 10:
                    await maintenance.heartbeat()
                    last_heartbeat = now
                deleted = await account_deletion.process_file_batch(limit=1)
                processed = bool(deleted) or await process_next_transcription()
                failures = 0
            except (DBAPIError, PoolTimeout, ConnectionError, TimeoutError, OSError):
                # Sem SQL, DSN, áudio, texto ou stack do provedor nos logs.
                logger.warning("worker_database_unavailable")
                await dispose_engine()
                if once:
                    raise
                failures += 1
                await asyncio.sleep(min(30, 2 ** min(failures, 5)) + random.random())
                continue
            if once:
                return
            if not processed:
                await asyncio.sleep(settings.assist_worker_poll_seconds)
    finally:
        await dispose_engine()
