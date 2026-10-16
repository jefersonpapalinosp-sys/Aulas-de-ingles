"""Capture the objects actually used, never reconstruct a past event from today's seed."""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import editorial_identity
from app.db.models import (
    CourseReview,
    CourseReviewAttempt,
    CourseReviewQuestion,
    EvidenceContentSnapshot,
    Exercise,
    ExerciseAttempt,
    LessonMedia,
    PracticeSession,
    PracticeSessionItem,
    SpeakingAttempt,
    TranscriptCue,
    WritingFeedbackRecord,
    WritingPrompt,
)
from app.domain.answers import analisar_resposta

EvidenceKind = Literal["exercise", "practice", "writing", "speaking", "checkpoint"]
PARENTS: dict[str, tuple[Any, str]] = {
    "exercise": (ExerciseAttempt, "exercise_attempt_id"),
    "practice": (PracticeSessionItem, "practice_item_id"),
    "writing": (WritingFeedbackRecord, "writing_feedback_id"),
    "speaking": (SpeakingAttempt, "speaking_attempt_id"),
    "checkpoint": (CourseReviewAttempt, "checkpoint_attempt_id"),
}


class HistoricalContentOut(BaseModel):
    evidence_kind: EvidenceKind
    evidence_id: int
    status: Literal["available", "unavailable"]
    schema_version: str | None = None
    captured_at: datetime | None = None
    content_sha256: str | None = None
    content: dict[str, Any] | None = None
    note: str


async def schema_available(session: AsyncSession) -> bool:
    # No process-wide negative cache: installing the migration must be observable.
    return bool(
        await session.scalar(text("SELECT to_regclass('public.evidence_content_snapshot')"))
    )


def exercise_content(exercise: Exercise) -> dict[str, Any]:
    return {
        "kind": "exercise",
        "source_id": exercise.id,
        "lesson_id": exercise.lesson_id,
        "position_at_capture": exercise.position,
        "prompt": exercise.prompt,
        "activity_type": exercise.activity_type,
        "skill": exercise.skill,
        "objective": exercise.objective,
        "options": exercise.options,
        "classification_items": exercise.classification_items,
        "classification_categories": exercise.classification_categories,
        "answers": [item.value for item in exercise.answers],
        "hint": exercise.hint,
        "hints": [{"level": hint.level, "content": hint.content} for hint in exercise.hints],
        "explanation": exercise.explanation,
    }


def exercise_result(exercise: Exercise, answer: str, correct: bool) -> dict[str, Any]:
    return {
        **exercise_content(exercise),
        "result": {
            "answer": answer,
            "correct": correct,
            "feedback": asdict(
                analisar_resposta(answer, [item.value for item in exercise.answers])
            ),
            "explanation": exercise.explanation if correct else None,
        },
        "algorithm_version": "answer-comparison-40B2-v1",
    }


def checkpoint_content(review: CourseReview) -> dict[str, Any]:
    return {
        "kind": "checkpoint",
        "source_id": review.id,
        "title": review.title,
        "unit_id": review.unit_id,
        "content_version": review.content_version,
        "source_kind": review.source_kind,
        "source_title": review.source_title,
        "source_url": review.source_url,
        "source_note": review.source_note,
        "intro": review.intro,
        "review_lesson_number": review.review_lesson_number,
        "listening_lesson_number": review.listening_lesson_number,
        "listening_media_position": review.listening_media_position,
        "listening_course_id": review.listening_course_id,
        "listening_lesson_id": review.listening_lesson_id,
        "listening_media_id": review.listening_media_id,
        "questions": [
            {
                field: getattr(question, field)
                for field in (
                    "id",
                    "position",
                    "activity_type",
                    "skill",
                    "prompt",
                    "options",
                    "accepted_answers",
                    "explanation",
                    "lesson_numbers",
                )
            }
            for question in review.questions
        ],
        "algorithm_version": "answer-comparison-40B2-v1",
    }


async def speaking_content(session: AsyncSession, cue: TranscriptCue) -> dict[str, Any]:
    # Use the already-loaded cue, not a later reread after upload/STT completion.
    media = (
        (
            await session.execute(
                select(
                    *[
                        column
                        for column in LessonMedia.__table__.c
                        if column.name != "editorial_key"
                    ]
                ).where(LessonMedia.id == cue.media_id)
            )
        )
        .mappings()
        .one()
    )
    return {
        "kind": "speaking",
        "source_id": cue.id,
        "media_id": cue.media_id,
        "position_at_capture": cue.position,
        "start_seconds": cue.start_seconds,
        "end_seconds": cue.end_seconds,
        "speaker": cue.speaker,
        "text_en": cue.text_en,
        "text_pt": cue.text_pt,
        "media": {
            field: (
                str(media[field])
                if field == "license_reviewed_at" and media[field]
                else media[field]
            )
            for field in (
                "lesson_id",
                "kind",
                "label",
                "source_url",
                "license_status",
                "license_url",
                "license_note",
                "attribution",
                "offline_policy",
                "license_reviewed_at",
            )
        },
    }


async def _with_editorial_keys(
    session: AsyncSession, kind: EvidenceKind, content: dict[str, Any]
) -> dict[str, Any]:
    """Only immutable metadata is reread; captured pedagogical content is untouched.

    Optional metadata within snapshot schema 1.0, explicitly tagged by its own
    contract. b40-only deployments omit it. Never upgrade old snapshots.
    """
    if not await editorial_identity.schema_available(session):
        return content
    if kind == "checkpoint":
        questions = content["questions"]
        keys = dict(
            (
                await session.execute(
                    select(CourseReviewQuestion.id, CourseReviewQuestion.editorial_key).where(
                        CourseReviewQuestion.id.in_([q["id"] for q in questions])
                    )
                )
            ).all()
        )
        return {
            **content,
            "editorial_identity_contract": "explicit_uuid_v1",
            "questions": [
                {**question, "editorial_key": keys[question["id"]]} for question in questions
            ],
        }
    model: Any = {
        "exercise": Exercise,
        "practice": Exercise,
        "writing": WritingPrompt,
        "speaking": TranscriptCue,
    }[kind]
    key = await session.scalar(select(model.editorial_key).where(model.id == content["source_id"]))
    if key is None:
        raise HTTPException(503, "Identidade editorial indisponível; operação não concluída.")
    result = {**content, "editorial_key": key, "editorial_identity_contract": "explicit_uuid_v1"}
    if kind == "speaking":
        media_key = await session.scalar(
            select(LessonMedia.editorial_key).where(LessonMedia.id == content["media_id"])
        )
        if media_key is None:
            raise HTTPException(503, "Identidade da mídia indisponível; operação não concluída.")
        result["media"] = {**content["media"], "editorial_key": media_key}
    return result


async def capture(
    session: AsyncSession,
    kind: EvidenceKind,
    evidence_id: int,
    user_id: int,
    content: dict[str, Any],
) -> None:
    if not get_settings().editorial_snapshots_enabled:
        return
    # If enabled against an unmigrated DB, fail/rollback instead of silently
    # acknowledging an event without its promised snapshot.
    if not await schema_available(session):
        raise HTTPException(503, "Histórico ainda não migrado; operação não concluída.")
    canonical = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    if len(canonical.encode()) > 200_000:
        raise HTTPException(413, "Conteúdo excede o limite do histórico; nada foi concluído.")
    enriched = await _with_editorial_keys(session, kind, content)
    canonical = json.dumps(
        enriched, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    if len(canonical.encode()) > 200_000:
        raise HTTPException(413, "Conteúdo excede o limite do histórico; nada foi concluído.")
    _, field = PARENTS[kind]
    session.add(
        EvidenceContentSnapshot(
            user_id=user_id,
            **{field: evidence_id},
            schema_version="1.0",
            content=json.loads(canonical),
            content_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        )
    )
    await session.flush()


async def stored_snapshot(
    session: AsyncSession,
    kind: EvidenceKind,
    evidence_id: int,
    user_id: int,
) -> EvidenceContentSnapshot | None:
    if not await schema_available(session):
        return None
    _, field = PARENTS[kind]
    return await session.scalar(
        select(EvidenceContentSnapshot).where(
            EvidenceContentSnapshot.user_id == user_id,
            getattr(EvidenceContentSnapshot, field) == evidence_id,
        )
    )


async def stored_snapshots(
    session: AsyncSession,
    kind: EvidenceKind,
    evidence_ids: list[int] | set[int],
    user_id: int,
) -> dict[int, EvidenceContentSnapshot]:
    """Return an ownership-scoped snapshot map without N+1 history queries."""
    if not evidence_ids or not await schema_available(session):
        return {}
    _, field = PARENTS[kind]
    parent_column = getattr(EvidenceContentSnapshot, field)
    rows = (
        await session.execute(
            select(EvidenceContentSnapshot).where(
                EvidenceContentSnapshot.user_id == user_id,
                parent_column.in_(evidence_ids),
            )
        )
    ).scalars()
    return {
        int(getattr(snapshot, field)): snapshot
        for snapshot in rows
        if getattr(snapshot, field) is not None
    }


def speaking_expected_text(snapshot: EvidenceContentSnapshot | None) -> str | None:
    """Read the cue captured with the attempt, never today's transcript cue."""
    if snapshot is None:
        return None
    content = snapshot.content
    value = content.get("text_en") if content.get("kind") == "speaking" else None
    return value if isinstance(value, str) and value.strip() else None


async def speaking_expected_texts(
    session: AsyncSession, attempt_ids: list[int] | set[int], user_id: int
) -> dict[int, str]:
    snapshots = await stored_snapshots(session, "speaking", attempt_ids, user_id)
    result: dict[int, str] = {}
    for attempt_id, snapshot in snapshots.items():
        value = speaking_expected_text(snapshot)
        if value is not None:
            result[attempt_id] = value
    return result


async def worker_speaking_expected_text(
    session: AsyncSession, attempt_id: int, user_id: int
) -> str | None:
    """Least-privilege projection used by the isolated transcription worker."""
    value = await session.scalar(
        text("SELECT public.aulas_speaking_expected_text(:attempt_id, :user_id)"),
        {"attempt_id": attempt_id, "user_id": user_id},
    )
    return value if isinstance(value, str) and value.strip() else None


async def get_history(
    session: AsyncSession,
    kind: EvidenceKind,
    evidence_id: int,
    user_id: int,
) -> HistoricalContentOut:
    parent, _ = PARENTS[kind]
    query = select(parent.id).where(parent.id == evidence_id)
    if kind == "practice":
        query = query.join(PracticeSession).where(PracticeSession.user_id == user_id)
    else:
        query = query.where(parent.user_id == user_id)
    if await session.scalar(query) is None:
        raise HTTPException(404, "Registro não existe.")
    snapshot = await stored_snapshot(session, kind, evidence_id, user_id)
    if snapshot is None:
        return HistoricalContentOut(
            evidence_kind=kind,
            evidence_id=evidence_id,
            status="unavailable",
            note="Conteúdo histórico não capturado. "
            "O conteúdo atual não foi usado para reconstruí-lo.",
        )
    content = dict(snapshot.content)
    redacted = False
    if kind == "practice":
        # An unfinished item is not an answer-reveal endpoint. Same private
        # content is exportable by the account owner, as are their other records.
        item = await session.get(PracticeSessionItem, evidence_id)
        assert item is not None
        if item.completed_at is None and item.answer_revealed_at is None:
            for field in ("answers", "hint", "hints", "explanation"):
                content.pop(field, None)
            content["correction_hidden"] = True
            redacted = True
    return HistoricalContentOut(
        evidence_kind=kind,
        evidence_id=evidence_id,
        status="available",
        schema_version=snapshot.schema_version,
        captured_at=snapshot.created_at,
        content_sha256=None if redacted else snapshot.content_sha256,
        content=content,
        note="Conteúdo capturado com o registro, não uma certificação de revisão pedagógica. "
        "Gabarito e hash podem ser ocultados enquanto a prática estiver pendente.",
    )
