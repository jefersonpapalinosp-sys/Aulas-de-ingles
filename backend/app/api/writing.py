"""Rascunhos, versões e feedback da produção escrita."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.assist import assisted_usage
from app.api.deps import UsuarioAtual
from app.api.review import adicionar_item_revisao
from app.core.config import get_settings
from app.db.models import (
    Lesson,
    SkillEvidence,
    WritingDraft,
    WritingFeedbackRecord,
    WritingPrompt,
    WritingRevision,
)
from app.db.session import get_session
from app.domain.writing import analyze_writing
from app.schemas.assist import HumanRatingIn
from app.schemas.writing import (
    WritingDraftIn,
    WritingDraftOut,
    WritingFeedbackCheckOut,
    WritingFeedbackIn,
    WritingFeedbackOut,
    WritingHistoryItemOut,
    WritingRevisionOut,
)
from app.services import assistance

router = APIRouter(prefix="/writing", tags=["writing"])


def _feedback_out(record: WritingFeedbackRecord) -> WritingFeedbackOut:
    return WritingFeedbackOut(
        id=record.id,
        word_count=record.word_count,
        sentence_count=record.sentence_count,
        ready=record.ready,
        checks=[WritingFeedbackCheckOut.model_validate(check) for check in record.checks],
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


async def _prompt(session: AsyncSession, prompt_id: int) -> WritingPrompt:
    prompt = (
        await session.execute(select(WritingPrompt).where(WritingPrompt.id == prompt_id))
    ).scalar_one_or_none()
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposta não existe.")
    return prompt


async def _draft(session: AsyncSession, prompt: WritingPrompt, user_id: int) -> WritingDraft | None:
    return (
        await session.execute(
            select(WritingDraft).where(
                WritingDraft.prompt_id == prompt.id, WritingDraft.user_id == user_id
            )
        )
    ).scalar_one_or_none()


def _draft_out(prompt_id: int, draft: WritingDraft | None) -> WritingDraftOut:
    if draft is None:
        return WritingDraftOut(prompt_id=prompt_id, text="", updated_at=None, revisions=[])
    return WritingDraftOut(
        prompt_id=prompt_id,
        text=draft.text,
        updated_at=draft.updated_at,
        revisions=[
            WritingRevisionOut.model_validate(revision, from_attributes=True)
            for revision in draft.revisions
        ],
    )


@router.get("/prompts/{prompt_id}/draft", response_model=WritingDraftOut)
async def obter_rascunho(
    prompt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WritingDraftOut:
    prompt = await _prompt(session, prompt_id)
    return _draft_out(prompt.id, await _draft(session, prompt, usuario.id))


@router.put("/prompts/{prompt_id}/draft", response_model=WritingDraftOut)
async def salvar_rascunho(
    prompt_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[WritingDraftIn, Body()],
) -> WritingDraftOut:
    prompt = await _prompt(session, prompt_id)
    draft = await _draft(session, prompt, usuario.id)
    if draft is None:
        draft = WritingDraft(user_id=usuario.id, prompt_id=prompt.id)
        session.add(draft)
    draft.text = corpo.text
    await session.commit()
    await session.refresh(draft)
    return _draft_out(prompt.id, draft)


@router.post("/prompts/{prompt_id}/versions", response_model=WritingRevisionOut)
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
    draft = await _draft(session, prompt, usuario.id)
    if draft is None:
        draft = WritingDraft(user_id=usuario.id, prompt_id=prompt.id, text=corpo.text)
        session.add(draft)
        await session.flush()
    else:
        draft.text = corpo.text

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
        return WritingRevisionOut.model_validate(latest, from_attributes=True)

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
    return WritingRevisionOut.model_validate(revision, from_attributes=True)


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
    if corpo.assisted:
        mode = "fallback"
        if not settings.assisted_features_enabled or not settings.assist_writing_url:
            assisted_error = "feature_disabled"
        else:
            used, _ = await assisted_usage(session, usuario.id)
            if used >= settings.assist_daily_quota:
                assisted_error = "quota_exceeded"
            else:
                provider = settings.assist_provider_name
                rubric = [
                    {"code": "word_count", "minimum": prompt.min_words},
                    {"code": "sentence_count", "minimum": prompt.min_sentences},
                    *prompt.requirements,
                ]
                try:
                    assisted = await asyncio.to_thread(
                        assistance.call_writing_provider,
                        settings.assist_writing_url,
                        corpo.text,
                        rubric,
                        token=settings.assist_provider_token,
                        timeout=settings.assist_timeout_seconds,
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

    record = WritingFeedbackRecord(
        user_id=usuario.id,
        prompt_id=prompt.id,
        text=corpo.text,
        word_count=word_count,
        sentence_count=sentence_count,
        ready=ready,
        checks=[check.__dict__ for check in checks],
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
    return _feedback_out(record)


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
    return _feedback_out(record)


@router.get("/history", response_model=list[WritingHistoryItemOut])
async def historico_de_escrita(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[WritingHistoryItemOut]:
    rows = (
        await session.execute(
            select(WritingDraft, WritingPrompt, Lesson)
            .join(WritingPrompt, WritingDraft.prompt_id == WritingPrompt.id)
            .join(Lesson, WritingPrompt.lesson_id == Lesson.id)
            .where(WritingDraft.user_id == usuario.id)
            .order_by(WritingDraft.updated_at.desc())
        )
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

    return [
        WritingHistoryItemOut(
            prompt_id=prompt.id,
            lesson_number=lesson.number,
            lesson_title=lesson.title,
            prompt_title=prompt.title,
            draft_text=draft.text,
            updated_at=draft.updated_at,
            revisions=[
                WritingRevisionOut.model_validate(revision, from_attributes=True)
                for revision in draft.revisions
            ],
            feedbacks=[_feedback_out(item) for item in feedback_by_prompt.get(prompt.id, [])],
        )
        for draft, prompt, lesson in rows
    ]
