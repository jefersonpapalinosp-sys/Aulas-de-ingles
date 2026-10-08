"""Fila durável de transcrição apoiada pelo PostgreSQL.

A API apenas persiste jobs. Um processo worker separado reivindica uma linha
com ``FOR UPDATE SKIP LOCKED``, chama o gateway fora da transação e grava o
resultado somente se ainda possuir aquela tentativa. Isso permite vários
workers, retomada após reinício e retry sem duplicar a requisição lógica.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models import SpeakingAttempt, TranscriptionJob
from app.db.session import dispose_engine, get_sessionmaker
from app.services import assistance
from app.services.audio_storage import AudioStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedJob:
    job_id: int
    attempt_number: int


async def _recover_stale_jobs(now: datetime) -> None:
    settings = get_settings()
    cutoff = now - timedelta(seconds=settings.assist_job_stale_seconds)
    async with get_sessionmaker()() as session, session.begin():
        retryable = (
            (TranscriptionJob.status == "processing")
            & (TranscriptionJob.processing_started_at <= cutoff)
            & (TranscriptionJob.attempt_count < TranscriptionJob.max_attempts)
        )
        await session.execute(
            update(TranscriptionJob)
            .where(retryable)
            .values(
                status="queued",
                error_code="worker_interrupted",
                next_attempt_at=now,
                processing_started_at=None,
            )
        )
        exhausted = (
            (
                (TranscriptionJob.status == "queued")
                | (
                    (TranscriptionJob.status == "processing")
                    & (TranscriptionJob.processing_started_at <= cutoff)
                )
            )
            & (TranscriptionJob.attempt_count >= TranscriptionJob.max_attempts)
        )
        await session.execute(
            update(TranscriptionJob)
            .where(exhausted)
            .values(
                status="failed",
                error_code="attempts_exhausted",
                processing_started_at=None,
                completed_at=now,
            )
        )


async def _claim_next_job(now: datetime) -> ClaimedJob | None:
    await _recover_stale_jobs(now)
    async with get_sessionmaker()() as session, session.begin():
        job = (
            await session.execute(
                select(TranscriptionJob)
                .where(
                    TranscriptionJob.status == "queued",
                    TranscriptionJob.next_attempt_at <= now,
                    TranscriptionJob.attempt_count < TranscriptionJob.max_attempts,
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
        return ClaimedJob(job_id=job.id, attempt_number=job.attempt_count)


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
        if retryable and job.attempt_count < job.max_attempts:
            delay = settings.assist_job_retry_base_seconds * (2 ** (job.attempt_count - 1))
            job.status = "queued"
            job.next_attempt_at = now + timedelta(seconds=delay)
            job.completed_at = None
        else:
            job.status = "failed"
            job.completed_at = now
        job.error_code = code
        job.processing_started_at = None


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
        if job is None:
            return
        job.status = "completed"
        job.transcript_text = result.text
        job.words = result.words
        job.mean_confidence = result.mean_confidence
        job.similarity_score = assistance.compare_transcript(expected_text, result.text)
        job.low_confidence = result.mean_confidence < 0.75
        job.cost_microusd = result.cost_microusd
        job.error_code = None
        job.processing_started_at = None
        job.completed_at = datetime.now(UTC)


async def process_next_transcription() -> bool:
    """Processa no máximo um job; retorna se algum registro foi reivindicado."""

    settings = get_settings()
    if not settings.assisted_features_enabled or not settings.assist_transcription_url:
        return False
    claim = await _claim_next_job(datetime.now(UTC))
    if claim is None:
        return False

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
                select(SpeakingAttempt)
                .options(selectinload(SpeakingAttempt.cue))
                .where(SpeakingAttempt.id == job.speaking_attempt_id)
            )
        ).scalar_one_or_none()
        if attempt is None or not attempt.storage_key or not attempt.mime_type:
            await _record_failure(claim, "audio_unavailable", retryable=False)
            return True
        idempotency_key = job.idempotency_key
        expected_text = attempt.cue.text_en
        mime_type = attempt.mime_type
        path = AudioStorage(settings.speaking_storage_dir).path(attempt.storage_key)

    if path is None:
        await _record_failure(claim, "audio_unavailable", retryable=False)
        return True
    try:
        result = await asyncio.to_thread(
            assistance.call_transcription_provider,
            settings.assist_transcription_url,
            path.read_bytes(),
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
    try:
        while True:
            processed = await process_next_transcription()
            if once:
                return
            if not processed:
                await asyncio.sleep(settings.assist_worker_poll_seconds)
    finally:
        await dispose_engine()
