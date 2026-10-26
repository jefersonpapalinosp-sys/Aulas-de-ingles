"""Feedback de produção escrita: rubrica local, assistência opcional, registro.

A rubrica determinística é a autoridade. O provedor externo só explica
pendências que a rubrica já detectou: recebe o resultado local pronto e nunca
cria critério novo nem altera a prontidão do texto. Qualquer falha dele
degrada para ``fallback`` sem descartar a análise local e sem vazar conteúdo na
mensagem de erro.

A ordem do caminho assistido é deliberada: reservar a cota, consumir, **fazer
commit da admissão** e só então chamar o provedor. Uma desconexão depois disso
não prova ausência de consumo, e o reenvio com a mesma ``operation_key`` devolve
o registro já gravado em vez de cobrar de novo.
"""

import asyncio
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, NamedTuple
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import SkillEvidence, User, WritingFeedbackRecord, WritingPrompt
from app.domain.writing import WritingCheck, analyze_writing, rubric_snapshot
from app.domain.writing_rubric import ALGORITHM_VERSION
from app.schemas.writing import WritingFeedbackIn
from app.services import assist_quota, assistance, editorial_history
from app.services.review import adicionar_item_revisao

AnalysisMode = Literal["deterministic", "fallback", "assisted"]


class Rubric(NamedTuple):
    """Resultado determinístico, calculado antes de qualquer assistência."""

    word_count: int
    sentence_count: int
    checks: list[WritingCheck]
    ready: bool
    version: str
    snapshot: dict[str, object]


@dataclass
class Assistance:
    """O que a assistência agregou — ou por que não agregou nada."""

    mode: AnalysisMode = "deterministic"
    provider: str | None = None
    summary: str | None = None
    suggestions: list[dict[str, object]] | None = None
    confidence: float | None = None
    cost_microusd: int = 0
    error: str | None = None
    reservation_id: int | None = None


class Replay(NamedTuple):
    """Reenvio da mesma ``operation_key``: o registro anterior, sem nova cobrança."""

    record: WritingFeedbackRecord


class FeedbackResult(NamedTuple):
    record: WritingFeedbackRecord
    historical_content_available: bool


def _rubric(prompt: WritingPrompt, text: str) -> Rubric:
    word_count, sentence_count, checks = analyze_writing(
        text,
        min_words=prompt.min_words,
        min_sentences=prompt.min_sentences,
        requirements=prompt.requirements,
    )
    version, snapshot = rubric_snapshot(
        title=prompt.title,
        instructions=prompt.instructions,
        min_words=prompt.min_words,
        min_sentences=prompt.min_sentences,
        requirements=prompt.requirements,
    )
    return Rubric(
        word_count=word_count,
        sentence_count=sentence_count,
        checks=list(checks),
        ready=all(check.passed for check in checks),
        version=version,
        snapshot=snapshot,
    )


def _fingerprint(prompt: WritingPrompt, rubric_version: str, text: str) -> str:
    return sha256(f"{prompt.id}:{rubric_version}:{ALGORITHM_VERSION}:{text}".encode()).hexdigest()


async def _previous_record(
    session: AsyncSession, user_id: int, reservation_id: int
) -> WritingFeedbackRecord | None:
    return (
        await session.execute(
            select(WritingFeedbackRecord).where(
                WritingFeedbackRecord.assist_reservation_id == reservation_id,
                WritingFeedbackRecord.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def _call_provider(
    text: str, rubric: list[dict[str, object]], provider_key: str
) -> assistance.WritingAssistResult:
    """Chama o provedor configurado. Fora da transação, por isso em ``to_thread``."""
    settings = get_settings()
    if settings.assist_provider_kind == "ollama":
        return await asyncio.to_thread(
            assistance.call_ollama_writing_provider,
            settings.assist_ollama_base_url,
            settings.assist_ollama_model,
            text,
            rubric,
            timeout=settings.assist_timeout_seconds,
        )
    gateway_url = settings.assist_writing_url
    if not gateway_url:
        raise assistance.ProviderFailure("provider_unavailable")
    return await asyncio.to_thread(
        assistance.call_writing_provider,
        gateway_url,
        text,
        rubric,
        token=settings.assist_provider_token,
        timeout=settings.assist_timeout_seconds,
        idempotency_key=provider_key,
    )


async def _assist(
    session: AsyncSession,
    usuario: User,
    prompt: WritingPrompt,
    corpo: WritingFeedbackIn,
    rubric: Rubric,
) -> Assistance | Replay:
    """Caminho assistido completo. ``Replay`` quando a operação já foi admitida."""
    settings = get_settings()
    result = Assistance(mode="fallback")
    if not settings.assisted_features_enabled or not settings.writing_assist_configured:
        result.error = "feature_disabled"
        return result

    try:
        reservation, created = await assist_quota.reserve(
            session,
            usuario.id,
            str(corpo.operation_key or uuid4()),
            _fingerprint(prompt, rubric.version, corpo.text),
            "writing",
        )
    except assist_quota.QuotaExceeded:
        result.error = "quota_exceeded"
        return result

    if not created:
        previous = await _previous_record(session, usuario.id, reservation.id)
        if previous is not None:
            return Replay(previous)
        raise HTTPException(409, "Análise já iniciada; consulte o histórico antes de reenviar.")

    result.reservation_id = reservation.id
    if not await assist_quota.consume(session, reservation.id):
        raise HTTPException(409, "Reserva expirada. Solicite uma nova análise.")
    # Persiste a admissão e devolve a conexão ANTES da chamada externa.
    # Uma desconexão/timeout posterior não prova ausência de consumo.
    await session.commit()
    result.provider = settings.assist_provider_name
    # O provedor recebe o resultado da rubrica local, não uma segunda cópia
    # incompleta das regras.
    local = [
        {
            "code": check.code,
            "label": check.label,
            "passed": check.passed,
            "suggestion": check.suggestion,
        }
        for check in rubric.checks
    ]
    try:
        assisted = await _call_provider(corpo.text, local, reservation.provider_key)
    except assistance.ProviderFailure as error:
        result.error = error.code
    except Exception:
        # Falha inesperada do gateway nunca descarta a rubrica local nem
        # devolve conteúdo sensível na mensagem.
        result.error = "internal_provider_error"
    else:
        result.mode = "assisted"
        result.summary = assisted.summary
        result.suggestions = assisted.suggestions
        result.confidence = assisted.confidence
        result.cost_microusd = assisted.cost_microusd
        if assisted.cost_known:
            await assist_quota.record_cost(session, reservation.id, result.cost_microusd)
    return result


def _record(
    usuario: User, prompt: WritingPrompt, text: str, rubric: Rubric, assist: Assistance
) -> WritingFeedbackRecord:
    return WritingFeedbackRecord(
        assist_reservation_id=assist.reservation_id,
        user_id=usuario.id,
        prompt_id=prompt.id,
        text=text,
        word_count=rubric.word_count,
        sentence_count=rubric.sentence_count,
        ready=rubric.ready,
        checks=[check.__dict__ for check in rubric.checks],
        algorithm_version=ALGORITHM_VERSION,
        rubric_version=rubric.version,
        rubric_snapshot=rubric.snapshot,
        analysis_mode=assist.mode,
        provider=assist.provider,
        assisted_summary=assist.summary,
        assisted_suggestions=assist.suggestions,
        assisted_confidence=assist.confidence,
        assisted_cost_microusd=assist.cost_microusd,
        assisted_error_code=assist.error,
    )


async def _capture_history(
    session: AsyncSession,
    usuario: User,
    prompt: WritingPrompt,
    record: WritingFeedbackRecord,
    rubric: Rubric,
    mode: AnalysisMode,
) -> None:
    await editorial_history.capture(
        session,
        "writing",
        record.id,
        usuario.id,
        {
            "kind": "writing",
            "source_id": prompt.id,
            "lesson_id": prompt.lesson_id,
            "rubric": rubric.snapshot,
            "rubric_version": rubric.version,
            "algorithm_version": ALGORITHM_VERSION,
            "checks": [check.__dict__ for check in rubric.checks],
            "ready": rubric.ready,
            "analysis_mode": mode,
        },
    )


def _evidence(usuario: User, record: WritingFeedbackRecord, rubric: Rubric) -> SkillEvidence:
    passed = sum(1 for check in rubric.checks if check.passed)
    score = passed / len(rubric.checks) if rubric.checks else (1.0 if rubric.ready else 0.0)
    return SkillEvidence(
        user_id=usuario.id,
        skill="writing",
        source_type="writing_feedback",
        source_id=record.id,
        score=score,
    )


async def _queue_review(session: AsyncSession, usuario: User, prompt: WritingPrompt) -> None:
    """Proposta com critério pendente volta à fila de revisão."""
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


async def gerar_feedback(
    session: AsyncSession, usuario: User, prompt: WritingPrompt, corpo: WritingFeedbackIn
) -> FeedbackResult:
    """Analisa ``corpo.text`` contra ``prompt`` e grava o registro resultante."""
    rubric = _rubric(prompt, corpo.text)
    assist = Assistance()
    if corpo.assisted:
        outcome = await _assist(session, usuario, prompt, corpo, rubric)
        if isinstance(outcome, Replay):
            snapshot = await editorial_history.stored_snapshot(
                session, "writing", outcome.record.id, usuario.id
            )
            return FeedbackResult(outcome.record, historical_content_available=snapshot is not None)
        assist = outcome

    record = _record(usuario, prompt, corpo.text, rubric, assist)
    session.add(record)
    await session.flush()
    await _capture_history(session, usuario, prompt, record, rubric, assist.mode)
    session.add(_evidence(usuario, record, rubric))
    if not rubric.ready:
        await _queue_review(session, usuario, prompt)
    await session.commit()
    await session.refresh(record)
    snapshot = await editorial_history.stored_snapshot(session, "writing", record.id, usuario.id)
    return FeedbackResult(record, historical_content_available=snapshot is not None)
