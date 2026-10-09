"""Checkpoints curriculares com resultado persistido por estudante."""

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.models import (
    Course,
    CourseReview,
    CourseReviewAttempt,
    CourseReviewQuestion,
    CourseUnit,
    Lesson,
    LessonMedia,
)
from app.db.session import get_session
from app.domain.answers import acertou
from app.schemas.course_review import (
    CourseReviewAttemptIn,
    CourseReviewAttemptOut,
    CourseReviewDetailOut,
    CourseReviewQuestionOut,
    CourseReviewQuestionResultOut,
)
from app.schemas.lesson import LessonMediaOut

router = APIRouter(prefix="/courses", tags=["course-reviews"])


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


async def _review_or_404(session: AsyncSession, course_slug: str, unit_slug: str) -> CourseReview:
    review = (
        await session.execute(
            select(CourseReview)
            .join(CourseUnit, CourseReview.unit_id == CourseUnit.id)
            .join(Course, CourseUnit.course_id == Course.id)
            .where(
                Course.slug == course_slug,
                Course.status == "published",
                CourseUnit.slug == unit_slug,
                CourseUnit.status == "published",
                CourseReview.status == "published",
            )
        )
    ).scalar_one_or_none()
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkpoint da unidade {course_slug!r}/{unit_slug!r} não existe.",
        )
    return review


async def _listening_media(
    session: AsyncSession, course_slug: str, review: CourseReview
) -> tuple[LessonMedia | None, str | None]:
    if review.listening_lesson_number is None or review.listening_media_position is None:
        return None, None
    row = (
        await session.execute(
            select(LessonMedia, Lesson.voa_url)
            .join(Lesson, LessonMedia.lesson_id == Lesson.id)
            .join(Course, Lesson.course_id == Course.id)
            .where(
                Course.slug == course_slug,
                Lesson.number == review.listening_lesson_number,
                LessonMedia.position == review.listening_media_position,
            )
        )
    ).one_or_none()
    if row is None:
        return None, None
    return row[0], row[1]


def _question_out(question: CourseReviewQuestion) -> CourseReviewQuestionOut:
    return CourseReviewQuestionOut.model_validate(
        {
            "id": question.id,
            "position": question.position,
            "activity_type": question.activity_type,
            "skill": question.skill,
            "prompt": question.prompt,
            "options": question.options,
            "lesson_numbers": question.lesson_numbers,
        }
    )


def _attempt_out(attempt: CourseReviewAttempt) -> CourseReviewAttemptOut:
    score_percent = round((attempt.score / attempt.total) * 100)
    feedback = [CourseReviewQuestionResultOut.model_validate(item) for item in attempt.result]
    reinforced = sorted(
        {
            lesson_number
            for item in feedback
            if not item.correct
            for lesson_number in item.lesson_numbers
        }
    )
    return CourseReviewAttemptOut(
        id=attempt.id,
        content_version=attempt.content_version,
        score=attempt.score,
        total=attempt.total,
        score_percent=score_percent,
        status="consolidated" if score_percent >= 80 else "reinforce",
        reinforced_lesson_numbers=reinforced,
        feedback=feedback,
        completed_at=attempt.completed_at,
    )


async def _latest_attempt(
    session: AsyncSession, review_id: int, user_id: int, content_version: int
) -> CourseReviewAttempt | None:
    return (
        await session.execute(
            select(CourseReviewAttempt)
            .where(
                CourseReviewAttempt.review_id == review_id,
                CourseReviewAttempt.user_id == user_id,
                CourseReviewAttempt.content_version == content_version,
            )
            .order_by(CourseReviewAttempt.completed_at.desc(), CourseReviewAttempt.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _detail_out(
    review: CourseReview,
    media: LessonMedia | None,
    listening_source_page_url: str | None,
    latest: CourseReviewAttempt | None,
) -> CourseReviewDetailOut:
    return CourseReviewDetailOut.model_validate(
        {
            "id": review.id,
            "slug": review.slug,
            "title": review.title,
            "position": review.position,
            "status": review.status,
            "source_kind": review.source_kind,
            "source_title": review.source_title,
            "source_url": review.source_url,
            "source_note": review.source_note,
            "intro": review.intro,
            "estimated_minutes": review.estimated_minutes,
            "content_version": review.content_version,
            "review_lesson_number": review.review_lesson_number,
            "listening_lesson_number": review.listening_lesson_number,
            "question_count": len(review.questions),
            "listening_media": LessonMediaOut.model_validate(media) if media else None,
            "listening_source_page_url": listening_source_page_url,
            "questions": [_question_out(question) for question in review.questions],
            "latest_attempt": _attempt_out(latest) if latest else None,
        }
    )


@router.get(
    "/{course_slug}/units/{unit_slug}/review",
    response_model=CourseReviewDetailOut,
)
async def get_course_review(
    course_slug: str,
    unit_slug: str,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> CourseReviewDetailOut:
    """Entrega questões sem gabarito e a tentativa mais recente da conta."""
    _private(response)
    review = await _review_or_404(session, course_slug, unit_slug)
    media, listening_source_page_url = await _listening_media(session, course_slug, review)
    latest = await _latest_attempt(session, review.id, usuario.id, review.content_version)
    return _detail_out(review, media, listening_source_page_url, latest)


def _request_hash(body: CourseReviewAttemptIn) -> str:
    payload = {
        "content_version": body.content_version,
        "answers": [
            {"question_id": answer.question_id, "answer": answer.answer}
            for answer in sorted(body.answers, key=lambda item: item.question_id)
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@router.post(
    "/{course_slug}/units/{unit_slug}/review/attempts",
    response_model=CourseReviewAttemptOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            "model": CourseReviewAttemptOut,
            "description": "A tentativa idempotente já existia.",
        }
    },
)
async def submit_course_review(
    course_slug: str,
    unit_slug: str,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    body: Annotated[CourseReviewAttemptIn, Body()],
    response: Response,
) -> CourseReviewAttemptOut:
    """Corrige a execução completa no servidor e persiste sua fotografia."""
    _private(response)
    review = await _review_or_404(session, course_slug, unit_slug)
    fingerprint = _request_hash(body)
    key = str(body.idempotency_key)
    existing = (
        await session.execute(
            select(CourseReviewAttempt).where(
                CourseReviewAttempt.user_id == usuario.id,
                CourseReviewAttempt.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.review_id != review.id or existing.request_hash != fingerprint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A chave de idempotência já foi usada com outro conteúdo.",
            )
        response.status_code = status.HTTP_200_OK
        return _attempt_out(existing)

    if body.content_version != review.content_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "course_review_content_changed",
                "current_version": review.content_version,
            },
        )

    questions = {question.id: question for question in review.questions}
    submitted = {answer.question_id: answer.answer for answer in body.answers}
    if set(submitted) != set(questions):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Envie exatamente uma resposta para cada questão do checkpoint.",
        )

    result: list[dict[str, object]] = []
    score = 0
    for question in review.questions:
        answer = submitted[question.id]
        correct = acertou(answer, question.accepted_answers)
        score += int(correct)
        result.append(
            {
                "question_id": question.id,
                "position": question.position,
                "correct": correct,
                "answer": answer,
                "accepted_answers": question.accepted_answers,
                "explanation": question.explanation,
                "lesson_numbers": question.lesson_numbers,
            }
        )

    attempt = CourseReviewAttempt(
        user_id=usuario.id,
        review_id=review.id,
        idempotency_key=key,
        request_hash=fingerprint,
        content_version=review.content_version,
        answers=[answer.model_dump() for answer in body.answers],
        result=result,
        score=score,
        total=len(questions),
    )
    session.add(attempt)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        concurrent = (
            await session.execute(
                select(CourseReviewAttempt).where(
                    CourseReviewAttempt.user_id == usuario.id,
                    CourseReviewAttempt.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        if (
            concurrent is None
            or concurrent.review_id != review.id
            or concurrent.request_hash != fingerprint
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Não foi possível registrar a tentativa idempotente.",
            ) from exc
        response.status_code = status.HTTP_200_OK
        return _attempt_out(concurrent)
    await session.refresh(attempt)
    return _attempt_out(attempt)
