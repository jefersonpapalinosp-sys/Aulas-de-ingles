"""Gravações opcionais da prática oral e transcrição experimental."""

import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated, Any
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
from sqlalchemy import Select, delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import UsuarioAtual
from app.core.config import get_settings
from app.db.models import (
    Course,
    CourseUnit,
    Lesson,
    LessonMedia,
    SkillEvidence,
    SpeakingAttempt,
    TranscriptCue,
    TranscriptionJob,
    User,
)
from app.db.session import get_session
from app.pagination import (
    PAGE_LIMIT_MAX,
    PAGINATED_ALTERNATIVE_HEADER,
    InvalidCursor,
    decode_time_id_cursor,
    encode_time_id_cursor,
)
from app.schemas.assist import HumanRatingIn, TranscriptionJobOut, TranscriptionWordOut
from app.schemas.speaking import (
    SpeakingAttemptIn,
    SpeakingAttemptOut,
    SpeakingAttemptPageOut,
    SpeakingPolicyOut,
)
from app.services import assist_quota, editorial_history
from app.services.audio_cleanup import discard_unreferenced_audio as _descartar_orfao
from app.services.audio_inspection import inspect_audio
from app.services.audio_storage import MIME_EXTENSIONS, AudioStorage, normalized_mime_type
from app.services.audio_upload import MAX_DURATION_MS, UPLOAD_TIMEOUT_SECONDS, read_audio
from app.services.curriculum import DEFAULT_COURSE_SLUG
from app.services.publication import (
    lock_publication,
    published_lesson_ids,
    require_published_lesson,
)
from app.services.review import adicionar_item_revisao

router = APIRouter(prefix="/speaking", tags=["speaking"])
logger = logging.getLogger(__name__)


def _query() -> Select[SpeakingAttempt]:
    """Tentativas de shadowing. Áudio de turno de diálogo (`origin='dialogue'`)
    não aparece aqui: ele pertence à visão do diálogo, tem outro contrato e
    outra retenção. O filtro é o que mantém `cue_id` não-nulo nesta rota."""
    return (
        select(SpeakingAttempt)
        .where(SpeakingAttempt.origin == "cue")
        .options(
            selectinload(SpeakingAttempt.cue)
            .selectinload(TranscriptCue.media)
            .selectinload(LessonMedia.lesson)
        )
    )


def _recorte[*Cols](
    query: Select[*Cols], *, lesson: int | None, course: str | None, unit: str | None
) -> Select[*Cols]:
    """Recorte de aula, curso e unidade — o mesmo na lista legada e na página.

    Sem ``course``, um filtro por aula vale no curso padrão: o número de aula
    só identifica uma aula dentro de um curso.
    """
    if lesson is not None:
        query = query.where(Lesson.number == lesson)
    if course is not None:
        query = query.where(Course.slug == course)
    elif lesson is not None:
        query = query.where(Course.slug == DEFAULT_COURSE_SLUG)
    if unit is not None:
        query = query.where(CourseUnit.slug == unit)
    return query


def _attempts_query(
    user_id: int,
    *,
    lesson: int | None,
    course: str | None,
    unit: str | None,
) -> Select[SpeakingAttempt]:
    query = _query().where(
        SpeakingAttempt.user_id == user_id,
        SpeakingAttempt.status == "ready",
    )
    if lesson is not None or course is not None or unit is not None:
        query = (
            query.join(SpeakingAttempt.cue)
            .join(TranscriptCue.media)
            .join(LessonMedia.lesson)
            .join(Lesson.course)
            .join(Lesson.unit)
        )
    return _recorte(query, lesson=lesson, course=course, unit=unit)


def _attempt_page_query(
    user_id: int,
    *,
    lesson: int | None,
    course: str | None,
    unit: str | None,
) -> Select[*tuple[Any, ...]]:
    query = (
        select(
            SpeakingAttempt.id,
            SpeakingAttempt.duration_ms,
            SpeakingAttempt.self_rating,
            SpeakingAttempt.consented_at,
            SpeakingAttempt.status,
            SpeakingAttempt.mime_type,
            SpeakingAttempt.file_size,
            SpeakingAttempt.created_at,
            SpeakingAttempt.integrity_state,
            TranscriptCue.id.label("cue_id"),
            Course.slug.label("course_slug"),
            Course.title.label("course_title"),
            CourseUnit.slug.label("unit_slug"),
            Lesson.number.label("lesson_number"),
        )
        .join(TranscriptCue, SpeakingAttempt.transcript_cue_id == TranscriptCue.id)
        .join(LessonMedia, TranscriptCue.media_id == LessonMedia.id)
        .join(Lesson, LessonMedia.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            SpeakingAttempt.user_id == user_id,
            SpeakingAttempt.status == "ready",
        )
    )
    return _recorte(query, lesson=lesson, course=course, unit=unit)


async def _active_jobs(
    session: AsyncSession,
    attempt_ids: list[int],
    user_id: int,
) -> dict[int, TranscriptionJob]:
    if not attempt_ids:
        return {}
    jobs = (
        await session.execute(
            select(TranscriptionJob).where(
                TranscriptionJob.user_id == user_id,
                TranscriptionJob.kind == "transcription",
                TranscriptionJob.speaking_attempt_id.in_(attempt_ids),
                TranscriptionJob.expires_at > datetime.now(UTC),
            )
        )
    ).scalars()
    # Job sem áudio é de diálogo por texto; não entra no mapa do shadowing.
    return {job.speaking_attempt_id: job for job in jobs if job.speaking_attempt_id}


async def _attempt_outputs(
    session: AsyncSession,
    attempts: list[SpeakingAttempt],
    user_id: int,
) -> list[SpeakingAttemptOut]:
    attempt_ids = [item.id for item in attempts]
    jobs_by_attempt = await _active_jobs(session, attempt_ids, user_id)
    captured_texts = await editorial_history.speaking_expected_texts(session, attempt_ids, user_id)
    return [
        _output(
            attempt,
            jobs_by_attempt.get(attempt.id),
            captured_texts.get(attempt.id),
        )
        for attempt in attempts
    ]


def _shadowing_cue(attempt: SpeakingAttempt) -> int:
    """O cue de uma tentativa de shadowing.

    As consultas destas rotas filtram `origin='cue'`, então o cue existe. Se
    algo escapar do filtro, 404 é a resposta certa — a gravação não existe
    *como shadowing* — e não um 500 por `None` onde o contrato pede `int`.
    """
    if attempt.transcript_cue_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gravação não existe.")
    return attempt.transcript_cue_id


def _job_attempt(job: TranscriptionJob) -> int:
    """O áudio de um job de transcrição; job de diálogo por texto não tem."""
    if job.speaking_attempt_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcrição não existe.")
    return job.speaking_attempt_id


def _transcription_out(job: TranscriptionJob, expected_text: str | None) -> TranscriptionJobOut:
    return TranscriptionJobOut(
        id=job.id,
        attempt_id=_job_attempt(job),
        status=job.status,
        provider=job.provider,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        next_attempt_at=job.next_attempt_at,
        expected_text=expected_text,
        historical_content_status="available" if expected_text is not None else "unavailable",
        transcript_text=job.transcript_text,
        words=[TranscriptionWordOut.model_validate(word) for word in (job.words or [])],
        mean_confidence=job.mean_confidence,
        similarity_score=job.similarity_score,
        low_confidence=job.low_confidence,
        error_code=job.error_code,
        cost_microusd=job.cost_microusd,
        human_rating=job.human_rating,
        requested_at=job.requested_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
    )


def _output(
    attempt: SpeakingAttempt,
    transcription: TranscriptionJob | None = None,
    captured_cue_text: str | None = None,
) -> SpeakingAttemptOut:
    return SpeakingAttemptOut(
        id=attempt.id,
        course_slug=attempt.cue.media.lesson.course.slug,
        course_title=attempt.cue.media.lesson.course.title,
        unit_slug=attempt.cue.media.lesson.unit.slug,
        lesson_number=attempt.cue.media.lesson.number,
        cue_id=_shadowing_cue(attempt),
        cue_text=captured_cue_text,
        historical_content_status=("available" if captured_cue_text is not None else "unavailable"),
        duration_ms=attempt.duration_ms,
        self_rating=attempt.self_rating,
        consented_at=attempt.consented_at,
        status=attempt.status,
        mime_type=attempt.mime_type,
        file_size=attempt.file_size,
        created_at=attempt.created_at,
        integrity_state=attempt.integrity_state,
        transcription=(
            _transcription_out(transcription, captured_cue_text) if transcription else None
        ),
    )


async def _captured_cue_text(session: AsyncSession, attempt_id: int, user_id: int) -> str | None:
    snapshot = await editorial_history.stored_snapshot(session, "speaking", attempt_id, user_id)
    return editorial_history.speaking_expected_text(snapshot)


async def _purge_expired_transcriptions(
    session: AsyncSession, user_id: int, attempt_id: int
) -> None:
    job = await session.scalar(
        select(TranscriptionJob)
        .where(
            TranscriptionJob.user_id == user_id,
            TranscriptionJob.speaking_attempt_id == attempt_id,
            TranscriptionJob.expires_at <= datetime.now(UTC),
        )
        .with_for_update()
    )
    if job is not None:
        await assist_quota.release(session, job.assist_reservation_id, "job_expired")
        await session.delete(job)
        await session.flush()


async def _owned_attempt(
    session: AsyncSession, attempt_id: int, user_id: int, *, lock: bool = False
) -> SpeakingAttempt:
    query = _query().where(SpeakingAttempt.id == attempt_id, SpeakingAttempt.user_id == user_id)
    if lock:
        query = query.with_for_update(of=SpeakingAttempt).execution_options(populate_existing=True)
    attempt = (await session.execute(query)).scalar_one_or_none()
    if attempt is None:
        # 404 não revela se a gravação existe em outra conta.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gravação não existe.")
    return attempt


@router.get("/policy", response_model=SpeakingPolicyOut)
async def politica_audio(response: Response) -> SpeakingPolicyOut:
    response.headers["Cache-Control"] = "no-store"
    return SpeakingPolicyOut(
        max_bytes=get_settings().speaking_max_bytes,
        max_duration_ms=MAX_DURATION_MS,
        mime_types=list(MIME_EXTENSIONS),
        upload_timeout_seconds=UPLOAD_TIMEOUT_SECONDS,
    )


@router.post("/attempts", response_model=SpeakingAttemptOut, status_code=status.HTTP_201_CREATED)
async def criar_tentativa(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[SpeakingAttemptIn, Body()],
) -> SpeakingAttemptOut:
    await lock_publication(session)
    cue = (
        await session.execute(
            select(TranscriptCue)
            .join(LessonMedia, TranscriptCue.media_id == LessonMedia.id)
            .where(
                TranscriptCue.id == corpo.cue_id,
                LessonMedia.lesson_id.in_(published_lesson_ids()),
            )
        )
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
    await session.flush()
    if get_settings().editorial_snapshots_enabled:
        await editorial_history.capture(
            session,
            "speaking",
            attempt.id,
            usuario.id,
            await editorial_history.speaking_content(session, cue),
        )
    await session.commit()
    saved = await _owned_attempt(session, attempt.id, usuario.id)
    return _output(
        saved,
        captured_cue_text=await _captured_cue_text(session, saved.id, usuario.id),
    )


RATING_SCORES = {"repeat": 0.35, "almost": 0.7, "confident": 1.0}


def _gravar_audio(
    attempt: SpeakingAttempt, data: bytes, mime_type: str, key: str, duration_ms: int
) -> None:
    """Marca a tentativa como pronta, com a integridade já conferida."""
    attempt.storage_key = key
    attempt.mime_type = mime_type
    attempt.file_size = len(data)
    attempt.audio_sha256 = sha256(data).hexdigest()
    attempt.integrity_state = "verified"
    attempt.integrity_checked_at = datetime.now(UTC)
    attempt.duration_ms = duration_ms
    attempt.status = "ready"


async def _evidencia_e_revisao(
    session: AsyncSession, usuario: User, attempt: SpeakingAttempt
) -> None:
    """Evidência de speaking e, se a autoavaliação não foi ``confident``, o
    retorno do trecho à fila de revisão."""
    session.add(
        SkillEvidence(
            user_id=usuario.id,
            skill="speaking",
            source_type="speaking_attempt",
            source_id=attempt.id,
            score=RATING_SCORES.get(attempt.self_rating or "", 0.5),
        )
    )
    if attempt.self_rating == "confident":
        return
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


@router.put("/attempts/{attempt_id}/audio", response_model=SpeakingAttemptOut)
async def enviar_audio(
    attempt_id: int,
    request: Request,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SpeakingAttemptOut:
    user_id = usuario.id
    await _owned_attempt(session, attempt_id, user_id)

    mime_type = normalized_mime_type(request.headers.get("content-type"))
    if mime_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato de áudio não suportado.",
        )
    settings = get_settings()
    # Não reter conexão/lock SQL durante recepção lenta. Só leituras até aqui.
    await session.commit()
    data = await read_audio(request, settings.speaking_max_bytes)
    # Decodificador não segura transação nem roda dentro do processo/event loop da API.
    duration_ms = await inspect_audio(data, mime_type)
    attempt = await _owned_attempt(session, attempt_id, user_id, lock=True)
    storage = AudioStorage(settings.speaking_storage_dir)
    if attempt.status == "ready":
        if attempt.mime_type == mime_type and storage.matches(attempt.storage_key, data):
            # Resposta perdida: mesmo corpo/tentativa, sem evidência nova.
            return _output(
                attempt,
                captured_cue_text=await _captured_cue_text(session, attempt.id, user_id),
            )
        raise HTTPException(409, "A tentativa já contém outro áudio. Não foi sobrescrita.")
    key = storage.save(data, mime_type)
    try:
        _gravar_audio(attempt, data, mime_type, key, duration_ms)
        await _evidencia_e_revisao(session, usuario, attempt)
        await session.commit()
    except Exception:
        await _descartar_orfao(session, storage, key)
        raise
    saved = await _owned_attempt(session, attempt.id, user_id)
    return _output(
        saved,
        captured_cue_text=await _captured_cue_text(session, saved.id, user_id),
    )


@router.get("/attempts", response_model=list[SpeakingAttemptOut])
async def listar_tentativas(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    lesson: Annotated[int | None, Query(ge=1)] = None,
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)] = PAGE_LIMIT_MAX,
) -> list[SpeakingAttemptOut]:
    """Lista legada com teto: devolve só a primeira página; o histórico completo vive em /page."""
    response.headers[PAGINATED_ALTERNATIVE_HEADER] = "/api/speaking/attempts/page"
    query = _attempts_query(
        usuario.id,
        lesson=lesson,
        course=course,
        unit=unit,
    )
    attempts = list(
        (
            await session.execute(query.order_by(SpeakingAttempt.created_at.desc()).limit(limit))
        ).scalars()
    )
    result = await _attempt_outputs(session, attempts, usuario.id)
    await session.commit()
    return result


@router.get("/attempts/page", response_model=SpeakingAttemptPageOut)
async def listar_tentativas_paginadas(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    lesson: Annotated[int | None, Query(ge=1)] = None,
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> SpeakingAttemptPageOut:
    boundary = None
    if cursor is not None:
        try:
            boundary = decode_time_id_cursor(cursor)
        except InvalidCursor as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_cursor", "message": "Cursor de paginação inválido."},
            ) from error
    query = _attempt_page_query(
        usuario.id,
        lesson=lesson,
        course=course,
        unit=unit,
    )
    if boundary is not None:
        query = query.where(
            tuple_(SpeakingAttempt.created_at, SpeakingAttempt.id)
            < tuple_(boundary.timestamp, boundary.row_id)
        )
    rows = (
        await session.execute(
            query.order_by(SpeakingAttempt.created_at.desc(), SpeakingAttempt.id.desc()).limit(
                limit + 1
            )
        )
    ).all()
    page = rows[:limit]
    attempt_ids = [row.id for row in page]
    jobs_by_attempt = await _active_jobs(session, attempt_ids, usuario.id)
    captured_texts = await editorial_history.speaking_expected_texts(
        session, attempt_ids, usuario.id
    )
    items = [
        SpeakingAttemptOut(
            id=row.id,
            course_slug=row.course_slug,
            course_title=row.course_title,
            unit_slug=row.unit_slug,
            lesson_number=row.lesson_number,
            cue_id=row.cue_id,
            cue_text=captured_texts.get(row.id),
            historical_content_status=("available" if row.id in captured_texts else "unavailable"),
            duration_ms=row.duration_ms,
            self_rating=row.self_rating,
            consented_at=row.consented_at,
            status=row.status,
            mime_type=row.mime_type,
            file_size=row.file_size,
            created_at=row.created_at,
            integrity_state=row.integrity_state,
            transcription=(
                _transcription_out(jobs_by_attempt[row.id], captured_texts.get(row.id))
                if row.id in jobs_by_attempt
                else None
            ),
        )
        for row in page
    ]
    await session.commit()
    return SpeakingAttemptPageOut(
        items=items,
        next_cursor=(
            encode_time_id_cursor(page[-1].created_at, page[-1].id)
            if len(rows) > limit and page
            else None
        ),
    )


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
    # Serializa a admissão e a procura de job existente na mesma conta.
    await assist_quota.lock_user(session, usuario.id)
    attempt = await _owned_attempt(session, attempt_id, usuario.id, lock=True)
    if (
        attempt.status != "ready"
        or not attempt.storage_key
        or attempt.integrity_state in {"missing", "changed"}
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Salve o áudio antes de pedir a transcrição.",
        )
    await _purge_expired_transcriptions(session, usuario.id, attempt_id)
    existing = (
        await session.execute(
            select(TranscriptionJob).where(
                TranscriptionJob.user_id == usuario.id,
                TranscriptionJob.speaking_attempt_id == attempt.id,
            )
        )
    ).scalar_one_or_none()
    expected_text = await _captured_cue_text(session, attempt.id, usuario.id)
    if existing is not None:
        await session.commit()
        return _transcription_out(existing, expected_text)
    await require_published_lesson(session, attempt.cue.media.lesson_id)
    if expected_text is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "historical_content_unavailable",
                "message": (
                    "O trecho usado nesta gravação não foi capturado. "
                    "Grave uma nova tentativa antes de solicitar a transcrição."
                ),
            },
        )
    try:
        reservation, _ = await assist_quota.reserve(
            session,
            usuario.id,
            str(uuid4()),
            sha256(f"transcription:{attempt.id}".encode()).hexdigest(),
            "transcription",
        )
    except assist_quota.QuotaExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Cota diária de análises assistidas atingida.",
        ) from error
    job = TranscriptionJob(
        assist_reservation_id=reservation.id,
        user_id=usuario.id,
        speaking_attempt_id=attempt.id,
        provider=settings.assist_provider_name,
        status="queued",
        idempotency_key=reservation.provider_key,
        max_attempts=settings.assist_job_max_attempts,
        next_attempt_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=settings.assist_retention_days),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    # O request-id desta linha liga a chamada HTTP ao identificador opaco que
    # reaparece no worker, sem persistir/logar texto, usuário, token ou áudio.
    logger.info("transcription_queued", extra={"job_id": job.id})
    return _transcription_out(job, expected_text)


async def _owned_transcription(
    session: AsyncSession, job_id: int, user_id: int, *, lock: bool = False
) -> TranscriptionJob:
    query = select(TranscriptionJob).where(
        TranscriptionJob.id == job_id,
        TranscriptionJob.user_id == user_id,
        # Job de diálogo não é transcrição de shadowing: 404 nestas rotas.
        TranscriptionJob.kind == "transcription",
        TranscriptionJob.expires_at > datetime.now(UTC),
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    job = (await session.execute(query)).scalar_one_or_none()
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
    attempt = await _owned_attempt(session, _job_attempt(job), usuario.id)
    job.human_rating = corpo.rating
    await session.commit()
    return _transcription_out(
        job,
        await _captured_cue_text(session, attempt.id, usuario.id),
    )


@router.delete("/transcriptions/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_transcricao(
    job_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    job = await _owned_transcription(session, job_id, usuario.id, lock=True)
    await assist_quota.release(session, job.assist_reservation_id, "cancelled_before_dispatch")
    await session.delete(job)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/attempts/{attempt_id}/audio")
async def obter_audio(
    attempt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    attempt = await _owned_attempt(session, attempt_id, usuario.id)
    if attempt.status != "ready" or not attempt.storage_key or not attempt.mime_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Áudio não existe.")
    settings = get_settings()
    key, digest, mime = attempt.storage_key, attempt.audio_sha256, attempt.mime_type
    await session.commit()
    try:
        data = AudioStorage(settings.speaking_storage_dir).read_verified(
            key, digest, settings.speaking_max_bytes
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Áudio não existe."
        ) from None
    except (OSError, ValueError):
        raise HTTPException(
            409, "Integridade do áudio não confirmada. Preserve a cópia local e grave novamente."
        ) from None
    return Response(data, media_type=mime)


@router.delete("/attempts/{attempt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_tentativa(
    attempt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    attempt = await _owned_attempt(session, attempt_id, usuario.id, lock=True)
    storage_key = attempt.storage_key
    jobs = (
        (
            await session.execute(
                select(TranscriptionJob)
                .where(
                    TranscriptionJob.speaking_attempt_id == attempt.id,
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    for job in jobs:
        await assist_quota.release(session, job.assist_reservation_id, "audio_deleted")
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
