"""Rascunhos, versões e feedback da produção escrita."""

import asyncio
from hashlib import sha256
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload

from app.api.concurrency import conflict, require_revision
from app.api.deps import UsuarioAtual
from app.api.errors import REVISION_REQUIRED_RESPONSES
from app.api.review import adicionar_item_revisao
from app.core.config import get_settings
from app.db.models import (
    Course,
    CourseUnit,
    Lesson,
    SkillEvidence,
    WritingDraft,
    WritingFeedbackRecord,
    WritingPrompt,
    WritingRevision,
)
from app.db.session import get_session
from app.domain.writing import analyze_writing, rubric_snapshot
from app.domain.writing_rubric import ALGORITHM_VERSION, EVALUATION_SCOPE
from app.pagination import (
    PAGE_LIMIT_MAX,
    PAGINATED_ALTERNATIVE_HEADER,
    InvalidCursor,
    TimeIdCursor,
    decode_time_id_cursor,
    encode_time_id_cursor,
)
from app.schemas.assist import HumanRatingIn
from app.schemas.writing import (
    WritingDraftIn,
    WritingDraftOut,
    WritingFeedbackCheckOut,
    WritingFeedbackIn,
    WritingFeedbackOut,
    WritingFeedbackPageOut,
    WritingHistoryItemOut,
    WritingHistoryPageOut,
    WritingHistorySummaryOut,
    WritingRevisionOut,
    WritingRevisionPageOut,
)
from app.services import assist_quota, assistance, editorial_history
from app.services.publication import (
    lock_publication,
    published_lesson_ids,
    require_published_lesson,
)

router = APIRouter(prefix="/writing", tags=["writing"])


def _feedback_out(
    record: WritingFeedbackRecord, *, historical_content_available: bool = False
) -> WritingFeedbackOut:
    return WritingFeedbackOut(
        source_text_hash=sha256(record.text.encode()).hexdigest(),
        id=record.id,
        word_count=record.word_count,
        sentence_count=record.sentence_count,
        ready=record.ready,
        checks=[WritingFeedbackCheckOut.model_validate(check) for check in record.checks],
        algorithm_version=record.algorithm_version,
        rubric_version=record.rubric_version,
        rubric_snapshot=record.rubric_snapshot,
        historical_content_status=("available" if historical_content_available else "unavailable"),
        evaluation_scope=EVALUATION_SCOPE,
        analysis_mode=record.analysis_mode,  # type: ignore[arg-type]
        evaluation_only=record.analysis_mode != "deterministic",
        provider=record.provider,
        assisted_summary=record.assisted_summary,
        assisted_suggestions=record.assisted_suggestions or [],
        assisted_confidence=record.assisted_confidence,
        low_confidence=(
            record.assisted_confidence is not None and record.assisted_confidence < 0.75
        ),
        assisted_cost_microusd=record.assisted_cost_microusd,
        assisted_error_code=record.assisted_error_code,
        human_rating=record.human_rating,  # type: ignore[arg-type]
        created_at=record.created_at,
    )


async def _prompt(
    session: AsyncSession, prompt_id: int, *, published_only: bool = True
) -> WritingPrompt:
    query = select(WritingPrompt).where(WritingPrompt.id == prompt_id)
    if published_only:
        await lock_publication(session)
        query = query.where(WritingPrompt.lesson_id.in_(published_lesson_ids()))
    prompt = (await session.execute(query)).scalar_one_or_none()
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposta não existe.")
    return prompt


async def _draft(session: AsyncSession, prompt: WritingPrompt, user_id: int) -> WritingDraft | None:
    return (
        await session.execute(
            select(WritingDraft)
            .options(raiseload(WritingDraft.revisions))
            .where(WritingDraft.prompt_id == prompt.id, WritingDraft.user_id == user_id)
        )
    ).scalar_one_or_none()


def _draft_out(prompt_id: int, draft: WritingDraft | None) -> WritingDraftOut:
    if draft is None:
        return WritingDraftOut(prompt_id=prompt_id, text="", updated_at=None)
    return WritingDraftOut(
        revision=draft.revision,
        prompt_id=prompt_id,
        text=draft.text,
        updated_at=draft.updated_at,
    )


def _cursor_boundary(cursor: str | None) -> TimeIdCursor | None:
    if cursor is None:
        return None
    try:
        return decode_time_id_cursor(cursor)
    except InvalidCursor as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_cursor", "message": "Cursor de paginação inválido."},
        ) from error


async def _locked_draft(
    session: AsyncSession, prompt: WritingPrompt, user_id: int, body: WritingDraftIn
) -> WritingDraft:
    require_revision(body.expected_revision)
    await session.execute(
        insert(WritingDraft)
        .values(
            user_id=user_id,
            prompt_id=prompt.id,
            text="",
            revision=0,
        )
        .on_conflict_do_nothing(constraint="uq_writing_draft_user_prompt")
    )
    draft = (
        await session.execute(
            select(WritingDraft)
            .options(raiseload(WritingDraft.revisions))
            .where(
                WritingDraft.prompt_id == prompt.id,
                WritingDraft.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if (
        body.expected_revision is not None
        and body.expected_revision != draft.revision
        and (body.text != draft.text or body.expected_revision > draft.revision)
    ):
        raise conflict(
            "draft_revision_conflict", _draft_out(prompt.id, draft).model_dump(mode="json")
        )
    if draft.text != body.text:
        draft.text = body.text
        draft.revision += 1
    return draft


@router.get("/prompts/{prompt_id}/draft", response_model=WritingDraftOut)
async def obter_rascunho(
    prompt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WritingDraftOut:
    prompt = await _prompt(session, prompt_id, published_only=False)
    draft = await _draft(session, prompt, usuario.id)
    if draft is None:
        await require_published_lesson(session, prompt.lesson_id)
    return _draft_out(prompt.id, draft)


@router.put(
    "/prompts/{prompt_id}/draft",
    response_model=WritingDraftOut,
    responses=REVISION_REQUIRED_RESPONSES,
)
async def salvar_rascunho(
    prompt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[WritingDraftIn, Body()],
) -> WritingDraftOut:
    prompt = await _prompt(session, prompt_id)
    draft = await _locked_draft(session, prompt, usuario.id, corpo)
    await session.commit()
    await session.refresh(draft)
    return _draft_out(prompt.id, draft)


@router.post(
    "/prompts/{prompt_id}/versions",
    response_model=WritingRevisionOut,
    responses=REVISION_REQUIRED_RESPONSES,
)
async def criar_versao(
    prompt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[WritingDraftIn, Body()],
) -> WritingRevisionOut:
    if not corpo.text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Texto vazio."
        )
    prompt = await _prompt(session, prompt_id)
    draft = await _locked_draft(session, prompt, usuario.id, corpo)

    latest = (
        await session.execute(
            select(WritingRevision)
            .where(WritingRevision.draft_id == draft.id)
            .order_by(WritingRevision.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None and latest.text == corpo.text:
        await session.commit()
        return WritingRevisionOut.model_validate(latest, from_attributes=True).model_copy(
            update={"draft_revision": draft.revision}
        )

    next_version = (
        await session.execute(
            select(func.coalesce(func.max(WritingRevision.version), 0)).where(
                WritingRevision.draft_id == draft.id
            )
        )
    ).scalar_one() + 1
    revision = WritingRevision(draft_id=draft.id, version=next_version, text=corpo.text)
    session.add(revision)
    await session.commit()
    await session.refresh(revision)
    return WritingRevisionOut.model_validate(revision, from_attributes=True).model_copy(
        update={"draft_revision": draft.revision}
    )


@router.get("/prompts/{prompt_id}/versions", response_model=WritingRevisionPageOut)
async def listar_versoes(
    prompt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> WritingRevisionPageOut:
    boundary = _cursor_boundary(cursor)
    query = (
        select(WritingRevision)
        .join(WritingDraft, WritingRevision.draft_id == WritingDraft.id)
        .where(
            WritingDraft.user_id == usuario.id,
            WritingDraft.prompt_id == prompt_id,
        )
    )
    if boundary is not None:
        query = query.where(
            tuple_(WritingRevision.created_at, WritingRevision.id)
            < tuple_(boundary.timestamp, boundary.row_id)
        )
    rows = list(
        (
            await session.execute(
                query.order_by(WritingRevision.created_at.desc(), WritingRevision.id.desc()).limit(
                    limit + 1
                )
            )
        ).scalars()
    )
    page = rows[:limit]
    return WritingRevisionPageOut(
        items=[WritingRevisionOut.model_validate(item, from_attributes=True) for item in page],
        next_cursor=(
            encode_time_id_cursor(page[-1].created_at, page[-1].id)
            if len(rows) > limit and page
            else None
        ),
    )


@router.post("/prompts/{prompt_id}/feedback", response_model=WritingFeedbackOut)
async def analisar_texto(
    prompt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[WritingFeedbackIn, Body()],
) -> WritingFeedbackOut:
    prompt = await _prompt(session, prompt_id)
    word_count, sentence_count, checks = analyze_writing(
        corpo.text,
        min_words=prompt.min_words,
        min_sentences=prompt.min_sentences,
        requirements=prompt.requirements,
    )
    ready = all(check.passed for check in checks)
    settings = get_settings()
    mode = "deterministic"
    provider: str | None = None
    assisted_summary: str | None = None
    assisted_suggestions: list[dict[str, object]] | None = None
    assisted_confidence: float | None = None
    assisted_cost = 0
    assisted_error: str | None = None
    reservation_id: int | None = None
    rubric_version, snapshot = rubric_snapshot(
        title=prompt.title,
        instructions=prompt.instructions,
        min_words=prompt.min_words,
        min_sentences=prompt.min_sentences,
        requirements=prompt.requirements,
    )
    if corpo.assisted:
        mode = "fallback"
        if not settings.assisted_features_enabled or not settings.writing_assist_configured:
            assisted_error = "feature_disabled"
        else:
            fingerprint = sha256(
                f"{prompt.id}:{rubric_version}:{ALGORITHM_VERSION}:{corpo.text}".encode()
            ).hexdigest()
            try:
                reservation, created = await assist_quota.reserve(
                    session,
                    usuario.id,
                    str(corpo.operation_key or uuid4()),
                    fingerprint,
                    "writing",
                )
            except assist_quota.QuotaExceeded:
                assisted_error = "quota_exceeded"
            else:
                if not created:
                    previous = (
                        await session.execute(
                            select(WritingFeedbackRecord).where(
                                WritingFeedbackRecord.assist_reservation_id == reservation.id,
                                WritingFeedbackRecord.user_id == usuario.id,
                            )
                        )
                    ).scalar_one_or_none()
                    if previous is not None:
                        history_snapshot = await editorial_history.stored_snapshot(
                            session, "writing", previous.id, usuario.id
                        )
                        return _feedback_out(
                            previous,
                            historical_content_available=history_snapshot is not None,
                        )
                    raise HTTPException(
                        409, "Análise já iniciada; consulte o histórico antes de reenviar."
                    )
                reservation_id = reservation.id
                provider_key = reservation.provider_key
                if not await assist_quota.consume(session, reservation_id):
                    raise HTTPException(409, "Reserva expirada. Solicite uma nova análise.")
                # Persiste a admissão e devolve a conexão ANTES da chamada externa.
                # Uma desconexão/timeout posterior não prova ausência de consumo.
                await session.commit()
                provider = settings.assist_provider_name
                # O provedor recebe o resultado da rubrica local, não uma
                # segunda cópia incompleta das regras. Assim ele só explica
                # pendências já detectadas deterministicamente e nunca cria
                # novos critérios ou altera a prontidão do texto.
                rubric = [
                    {
                        "code": check.code,
                        "label": check.label,
                        "passed": check.passed,
                        "suggestion": check.suggestion,
                    }
                    for check in checks
                ]
                try:
                    if settings.assist_provider_kind == "ollama":
                        assisted = await asyncio.to_thread(
                            assistance.call_ollama_writing_provider,
                            settings.assist_ollama_base_url,
                            settings.assist_ollama_model,
                            corpo.text,
                            rubric,
                            timeout=settings.assist_timeout_seconds,
                        )
                    else:
                        gateway_url = settings.assist_writing_url
                        if not gateway_url:
                            raise assistance.ProviderFailure("provider_unavailable")
                        assisted = await asyncio.to_thread(
                            assistance.call_writing_provider,
                            gateway_url,
                            corpo.text,
                            rubric,
                            token=settings.assist_provider_token,
                            timeout=settings.assist_timeout_seconds,
                            idempotency_key=provider_key,
                        )
                except assistance.ProviderFailure as error:
                    assisted_error = error.code
                except Exception:
                    # Falha inesperada do gateway nunca descarta a rubrica local
                    # nem devolve conteúdo sensível na mensagem.
                    assisted_error = "internal_provider_error"
                else:
                    mode = "assisted"
                    assisted_summary = assisted.summary
                    assisted_suggestions = assisted.suggestions
                    assisted_confidence = assisted.confidence
                    assisted_cost = assisted.cost_microusd
                    if assisted.cost_known:
                        await assist_quota.record_cost(session, reservation_id, assisted_cost)
    record = WritingFeedbackRecord(
        assist_reservation_id=reservation_id,
        user_id=usuario.id,
        prompt_id=prompt.id,
        text=corpo.text,
        word_count=word_count,
        sentence_count=sentence_count,
        ready=ready,
        checks=[check.__dict__ for check in checks],
        algorithm_version=ALGORITHM_VERSION,
        rubric_version=rubric_version,
        rubric_snapshot=snapshot,
        analysis_mode=mode,
        provider=provider,
        assisted_summary=assisted_summary,
        assisted_suggestions=assisted_suggestions,
        assisted_confidence=assisted_confidence,
        assisted_cost_microusd=assisted_cost,
        assisted_error_code=assisted_error,
    )
    session.add(record)
    await session.flush()
    await editorial_history.capture(
        session,
        "writing",
        record.id,
        usuario.id,
        {
            "kind": "writing",
            "source_id": prompt.id,
            "lesson_id": prompt.lesson_id,
            "rubric": snapshot,
            "rubric_version": rubric_version,
            "algorithm_version": ALGORITHM_VERSION,
            "checks": [check.__dict__ for check in checks],
            "ready": ready,
            "analysis_mode": mode,
        },
    )
    passed = sum(1 for check in checks if check.passed)
    score = passed / len(checks) if checks else (1.0 if ready else 0.0)
    session.add(
        SkillEvidence(
            user_id=usuario.id,
            skill="writing",
            source_type="writing_feedback",
            source_id=record.id,
            score=score,
        )
    )
    if not ready:
        await adicionar_item_revisao(
            session,
            usuario,
            lesson_id=prompt.lesson_id,
            item_type="writing_prompt",
            source_type="writing_prompt",
            source_id=prompt.id,
            source_key=f"writing-prompt:{prompt.id}",
            skill="writing",
            prompt=prompt.title,
            prompt_note=prompt.instructions,
            answer="; ".join(str(requirement["label"]) for requirement in prompt.requirements),
            context="Revise os critérios pendentes e escreva uma nova versão.",
            origin_reason=(
                "Esta proposta voltou porque o último texto ainda tinha critérios pendentes."
            ),
            estimated_seconds=8 * 60,
        )
    await session.commit()
    await session.refresh(record)
    history_snapshot = await editorial_history.stored_snapshot(
        session, "writing", record.id, usuario.id
    )
    return _feedback_out(
        record,
        historical_content_available=history_snapshot is not None,
    )


@router.put("/feedback/{feedback_id}/rating", response_model=WritingFeedbackOut)
async def avaliar_feedback(
    feedback_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[HumanRatingIn, Body()],
) -> WritingFeedbackOut:
    record = (
        await session.execute(
            select(WritingFeedbackRecord).where(
                WritingFeedbackRecord.id == feedback_id,
                WritingFeedbackRecord.user_id == usuario.id,
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback não existe.")
    if record.analysis_mode != "assisted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Somente feedback assistido participa da avaliação humana.",
        )
    record.human_rating = corpo.rating
    await session.commit()
    history_snapshot = await editorial_history.stored_snapshot(
        session, "writing", record.id, usuario.id
    )
    return _feedback_out(record, historical_content_available=history_snapshot is not None)


@router.get("/prompts/{prompt_id}/feedback", response_model=WritingFeedbackPageOut)
async def listar_feedbacks(
    prompt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> WritingFeedbackPageOut:
    boundary = _cursor_boundary(cursor)
    query = select(WritingFeedbackRecord).where(
        WritingFeedbackRecord.user_id == usuario.id,
        WritingFeedbackRecord.prompt_id == prompt_id,
    )
    if boundary is not None:
        query = query.where(
            tuple_(WritingFeedbackRecord.created_at, WritingFeedbackRecord.id)
            < tuple_(boundary.timestamp, boundary.row_id)
        )
    rows = list(
        (
            await session.execute(
                query.order_by(
                    WritingFeedbackRecord.created_at.desc(), WritingFeedbackRecord.id.desc()
                ).limit(limit + 1)
            )
        ).scalars()
    )
    page = rows[:limit]
    snapshots = await editorial_history.stored_snapshots(
        session, "writing", [item.id for item in page], usuario.id
    )
    return WritingFeedbackPageOut(
        items=[
            _feedback_out(item, historical_content_available=item.id in snapshots) for item in page
        ],
        next_cursor=(
            encode_time_id_cursor(page[-1].created_at, page[-1].id)
            if len(rows) > limit and page
            else None
        ),
    )


@router.get("/history/page", response_model=WritingHistoryPageOut)
async def historico_de_escrita_paginado(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
) -> WritingHistoryPageOut:
    boundary = _cursor_boundary(cursor)
    revision_count = (
        select(func.count(WritingRevision.id))
        .where(WritingRevision.draft_id == WritingDraft.id)
        .correlate(WritingDraft)
        .scalar_subquery()
    )
    feedback_count = (
        select(func.count(WritingFeedbackRecord.id))
        .where(
            WritingFeedbackRecord.user_id == WritingDraft.user_id,
            WritingFeedbackRecord.prompt_id == WritingPrompt.id,
        )
        .correlate(WritingDraft, WritingPrompt)
        .scalar_subquery()
    )
    query = (
        select(
            WritingDraft.id,
            WritingPrompt.id.label("prompt_id"),
            Course.slug.label("course_slug"),
            Course.title.label("course_title"),
            CourseUnit.slug.label("unit_slug"),
            Lesson.number.label("lesson_number"),
            Lesson.title.label("lesson_title"),
            WritingPrompt.title.label("prompt_title"),
            WritingDraft.updated_at,
            revision_count.label("revision_count"),
            feedback_count.label("feedback_count"),
        )
        .join(WritingPrompt, WritingDraft.prompt_id == WritingPrompt.id)
        .join(Lesson, WritingPrompt.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(WritingDraft.user_id == usuario.id)
    )
    if course is not None:
        query = query.where(Course.slug == course)
    if unit is not None:
        query = query.where(CourseUnit.slug == unit)
    if boundary is not None:
        query = query.where(
            tuple_(WritingDraft.updated_at, WritingDraft.id)
            < tuple_(boundary.timestamp, boundary.row_id)
        )
    rows = (
        await session.execute(
            query.order_by(WritingDraft.updated_at.desc(), WritingDraft.id.desc()).limit(limit + 1)
        )
    ).all()
    page = rows[:limit]
    return WritingHistoryPageOut(
        items=[WritingHistorySummaryOut.model_validate(row._mapping) for row in page],
        next_cursor=(
            encode_time_id_cursor(page[-1].updated_at, page[-1].id)
            if len(rows) > limit and page
            else None
        ),
    )


@router.get("/history", response_model=list[WritingHistoryItemOut])
async def historico_de_escrita(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    course: Annotated[str | None, Query(max_length=100)] = None,
    unit: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)] = PAGE_LIMIT_MAX,
) -> list[WritingHistoryItemOut]:
    """Lista legada com teto: devolve só a primeira página; o histórico completo vive em /page."""
    response.headers[PAGINATED_ALTERNATIVE_HEADER] = "/api/writing/history/page"
    history = (
        select(WritingDraft, WritingPrompt, Lesson)
        .join(WritingPrompt, WritingDraft.prompt_id == WritingPrompt.id)
        .join(Lesson, WritingPrompt.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(WritingDraft.user_id == usuario.id)
    )
    if course is not None:
        history = history.where(Course.slug == course)
    if unit is not None:
        history = history.where(CourseUnit.slug == unit)
    rows = (
        await session.execute(history.order_by(WritingDraft.updated_at.desc()).limit(limit))
    ).all()
    prompt_ids = [prompt.id for _, prompt, _ in rows]
    feedback_by_prompt: dict[int, list[WritingFeedbackRecord]] = {}
    if prompt_ids:
        feedbacks = (
            await session.execute(
                select(WritingFeedbackRecord)
                .where(
                    WritingFeedbackRecord.user_id == usuario.id,
                    WritingFeedbackRecord.prompt_id.in_(prompt_ids),
                )
                .order_by(WritingFeedbackRecord.created_at.desc())
            )
        ).scalars()
        for feedback in feedbacks:
            feedback_by_prompt.setdefault(feedback.prompt_id, []).append(feedback)

    feedback_ids = [feedback.id for items in feedback_by_prompt.values() for feedback in items]
    snapshots = await editorial_history.stored_snapshots(
        session, "writing", feedback_ids, usuario.id
    )

    return [
        WritingHistoryItemOut(
            prompt_id=prompt.id,
            course_slug=lesson.course.slug,
            course_title=lesson.course.title,
            unit_slug=lesson.unit.slug,
            lesson_number=lesson.number,
            lesson_title=lesson.title,
            prompt_title=prompt.title,
            draft_text=draft.text,
            updated_at=draft.updated_at,
            revisions=[
                WritingRevisionOut.model_validate(revision, from_attributes=True)
                for revision in draft.revisions
            ],
            feedbacks=[
                _feedback_out(
                    item,
                    historical_content_available=item.id in snapshots,
                )
                for item in feedback_by_prompt.get(prompt.id, [])
            ],
        )
        for draft, prompt, lesson in rows
    ]
