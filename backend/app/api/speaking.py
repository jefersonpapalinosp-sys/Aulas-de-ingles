"""Gravações opcionais da prática oral e transcrição experimental."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.assist import assisted_usage
from app.api.deps import UsuarioAtual
from app.api.review import adicionar_item_revisao
from app.core.config import get_settings
from app.db.models import (
    LessonMedia,
    SkillEvidence,
    SpeakingAttempt,
    TranscriptCue,
    TranscriptionJob,
)
from app.db.session import get_session
from app.schemas.assist import HumanRatingIn, TranscriptionJobOut, TranscriptionWordOut
from app.schemas.speaking import SpeakingAttemptIn, SpeakingAttemptOut
from app.services.audio_storage import AudioStorage, normalized_mime_type

router = APIRouter(prefix="/speaking", tags=["speaking"])


def _query() -> Select[SpeakingAttempt]:
    return select(SpeakingAttempt).options(
        selectinload(SpeakingAttempt.cue)
        .selectinload(TranscriptCue.media)
        .selectinload(LessonMedia.lesson)
    )


def _transcription_out(job: TranscriptionJob, expected_text: str) -> TranscriptionJobOut:
    return TranscriptionJobOut(
        id=job.id,
        attempt_id=job.speaking_attempt_id,
        status=job.status,  # type: ignore[arg-type]
        provider=job.provider,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        next_attempt_at=job.next_attempt_at,
        expected_text=expected_text,
        transcript_text=job.transcript_text,
        words=[TranscriptionWordOut.model_validate(word) for word in (job.words or [])],
        mean_confidence=job.mean_confidence,
        similarity_score=job.similarity_score,
        low_confidence=job.low_confidence,
        error_code=job.error_code,
        cost_microusd=job.cost_microusd,
        human_rating=job.human_rating,  # type: ignore[arg-type]
        requested_at=job.requested_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
    )


def _output(
    attempt: SpeakingAttempt, transcription: TranscriptionJob | None = None
) -> SpeakingAttemptOut:
    return SpeakingAttemptOut(
        id=attempt.id,
        lesson_number=attempt.cue.media.lesson.number,
        cue_id=attempt.transcript_cue_id,
        cue_text=attempt.cue.text_en,
        duration_ms=attempt.duration_ms,
        self_rating=attempt.self_rating,  # type: ignore[arg-type]
        consented_at=attempt.consented_at,
        status=attempt.status,  # type: ignore[arg-type]
        mime_type=attempt.mime_type,
        file_size=attempt.file_size,
        created_at=attempt.created_at,
        transcription=(
            _transcription_out(transcription, attempt.cue.text_en) if transcription else None
        ),
    )


async def _purge_expired_transcriptions(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        delete(TranscriptionJob).where(
            TranscriptionJob.user_id == user_id,
            TranscriptionJob.expires_at < datetime.now(UTC),
        )
    )


async def _owned_attempt(session: AsyncSession, attempt_id: int, user_id: int) -> SpeakingAttempt:
    attempt = (
        await session.execute(
            _query().where(
                SpeakingAttempt.id == attempt_id,
                SpeakingAttempt.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if attempt is None:
        # 404 não revela se a gravação existe em outra conta.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gravação não existe.")
    return attempt


@router.post("/attempts", response_model=SpeakingAttemptOut, status_code=status.HTTP_201_CREATED)
async def criar_tentativa(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[SpeakingAttemptIn, Body()],
) -> SpeakingAttemptOut:
    cue = (
        await session.execute(select(TranscriptCue).where(TranscriptCue.id == corpo.cue_id))
    ).scalar_one_or_none()
    if cue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trecho não existe.")

    attempt = SpeakingAttempt(
        user_id=usuario.id,
        transcript_cue_id=cue.id,
        duration_ms=corpo.duration_ms,
        self_rating=corpo.self_rating,
        status="pending",
    )
    session.add(attempt)
    await session.commit()
    return _output(await _owned_attempt(session, attempt.id, usuario.id))


@router.put("/attempts/{attempt_id}/audio", response_model=SpeakingAttemptOut)
async def enviar_audio(
    attempt_id: int,
    request: Request,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SpeakingAttemptOut:
    attempt = await _owned_attempt(session, attempt_id, usuario.id)
    if attempt.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Áudio já enviado.")

    mime_type = normalized_mime_type(request.headers.get("content-type"))
    if mime_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato de áudio não suportado.",
        )
    settings = get_settings()
    declared_size = request.headers.get("content-length")
    if (
        declared_size
        and declared_size.isdigit()
        and int(declared_size) > settings.speaking_max_bytes
    ):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Áudio excede o limite de 2 MB.",
        )
    data = await request.body()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Áudio vazio."
        )
    if len(data) > settings.speaking_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Áudio excede o limite de 2 MB.",
        )

    storage = AudioStorage(settings.speaking_storage_dir)
    key = storage.save(data, mime_type)
    try:
        attempt.storage_key = key
        attempt.mime_type = mime_type
        attempt.file_size = len(data)
        attempt.status = "ready"
        rating_scores = {"repeat": 0.35, "almost": 0.7, "confident": 1.0}
        session.add(
            SkillEvidence(
                user_id=usuario.id,
                skill="speaking",
                source_type="speaking_attempt",
                source_id=attempt.id,
                score=rating_scores.get(attempt.self_rating or "", 0.5),
            )
        )
        if attempt.self_rating != "confident":
            cue = attempt.cue
            await adicionar_item_revisao(
                session,
                usuario,
                lesson_id=cue.media.lesson_id,
                item_type="speaking_prompt",
                source_type="transcript_cue",
                source_id=cue.id,
                source_key=f"speaking-cue:{cue.id}",
                skill="speaking",
                prompt=cue.text_pt,
                prompt_note=f"{cue.speaker} · pratique por shadowing",
                answer=cue.text_en,
                context="Ouça o trecho, repita e compare ritmo e pronúncia.",
                origin_reason="Este trecho voltou após sua autoavaliação de speaking.",
                estimated_seconds=3 * 60,
                media_url=cue.media.source_url,
                cue_start_seconds=cue.start_seconds,
                cue_end_seconds=cue.end_seconds,
            )
        await session.commit()
    except Exception:
        storage.delete(key)
        raise
    return _output(await _owned_attempt(session, attempt.id, usuario.id))


@router.get("/attempts", response_model=list[SpeakingAttemptOut])
async def listar_tentativas(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    lesson: Annotated[int | None, Query(ge=1)] = None,
) -> list[SpeakingAttemptOut]:
    await _purge_expired_transcriptions(session, usuario.id)
    query = _query().where(
        SpeakingAttempt.user_id == usuario.id,
        SpeakingAttempt.status == "ready",
    )
    if lesson is not None:
        query = (
            query.join(SpeakingAttempt.cue)
            .join(TranscriptCue.media)
            .where(LessonMedia.lesson.has(number=lesson))
        )
    attempts = list(
        (await session.execute(query.order_by(SpeakingAttempt.created_at.desc()))).scalars()
    )
    jobs_by_attempt: dict[int, TranscriptionJob] = {}
    if attempts:
        jobs = (
            await session.execute(
                select(TranscriptionJob).where(
                    TranscriptionJob.user_id == usuario.id,
                    TranscriptionJob.speaking_attempt_id.in_([item.id for item in attempts]),
                )
            )
        ).scalars()
        jobs_by_attempt = {job.speaking_attempt_id: job for job in jobs}
    await session.commit()
    return [_output(attempt, jobs_by_attempt.get(attempt.id)) for attempt in attempts]


@router.post(
    "/attempts/{attempt_id}/transcription",
    response_model=TranscriptionJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def solicitar_transcricao(
    attempt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TranscriptionJobOut:
    settings = get_settings()
    if not settings.assisted_features_enabled or not settings.assist_transcription_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Transcrição assistida não está habilitada.",
        )
    attempt = await _owned_attempt(session, attempt_id, usuario.id)
    if attempt.status != "ready" or not attempt.storage_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Salve o áudio antes de pedir a transcrição.",
        )
    await _purge_expired_transcriptions(session, usuario.id)
    existing = (
        await session.execute(
            select(TranscriptionJob).where(
                TranscriptionJob.user_id == usuario.id,
                TranscriptionJob.speaking_attempt_id == attempt.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        await session.commit()
        return _transcription_out(existing, attempt.cue.text_en)
    used, _ = await assisted_usage(session, usuario.id)
    if used >= settings.assist_daily_quota:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Cota diária de análises assistidas atingida.",
        )
    job = TranscriptionJob(
        user_id=usuario.id,
        speaking_attempt_id=attempt.id,
        provider=settings.assist_provider_name,
        status="queued",
        idempotency_key=f"transcription-{uuid4().hex}",
        max_attempts=settings.assist_job_max_attempts,
        next_attempt_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=settings.assist_retention_days),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return _transcription_out(job, attempt.cue.text_en)


async def _owned_transcription(
    session: AsyncSession, job_id: int, user_id: int
) -> TranscriptionJob:
    job = (
        await session.execute(
            select(TranscriptionJob).where(
                TranscriptionJob.id == job_id,
                TranscriptionJob.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcrição não existe.")
    return job


@router.put("/transcriptions/{job_id}/rating", response_model=TranscriptionJobOut)
async def avaliar_transcricao(
    job_id: int,
    corpo: Annotated[HumanRatingIn, Body()],
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TranscriptionJobOut:
    job = await _owned_transcription(session, job_id, usuario.id)
    attempt = await _owned_attempt(session, job.speaking_attempt_id, usuario.id)
    job.human_rating = corpo.rating
    await session.commit()
    return _transcription_out(job, attempt.cue.text_en)


@router.delete("/transcriptions/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_transcricao(
    job_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    job = await _owned_transcription(session, job_id, usuario.id)
    await session.delete(job)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/attempts/{attempt_id}/audio")
async def obter_audio(
    attempt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FileResponse:
    attempt = await _owned_attempt(session, attempt_id, usuario.id)
    if attempt.status != "ready" or not attempt.storage_key or not attempt.mime_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Áudio não existe.")
    path = AudioStorage(get_settings().speaking_storage_dir).path(attempt.storage_key)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Áudio não existe.")
    return FileResponse(path, media_type=attempt.mime_type)


@router.delete("/attempts/{attempt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_tentativa(
    attempt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    attempt = await _owned_attempt(session, attempt_id, usuario.id)
    storage_key = attempt.storage_key
    await session.execute(
        delete(SkillEvidence).where(
            SkillEvidence.user_id == usuario.id,
            SkillEvidence.source_type == "speaking_attempt",
            SkillEvidence.source_id == attempt.id,
        )
    )
    await session.delete(attempt)
    await session.commit()
    AudioStorage(get_settings().speaking_storage_dir).delete(storage_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
