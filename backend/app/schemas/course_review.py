"""Contratos do checkpoint curricular de uma unidade."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.lesson import CourseReviewSummaryOut, LessonMediaOut


class CourseReviewQuestionOut(BaseModel):
    id: int
    position: int
    activity_type: Literal["multiple_choice", "short_answer"]
    skill: Literal["grammar", "listening", "vocabulary"]
    prompt: str
    options: list[str] | None
    lesson_numbers: list[int]


class CourseReviewAnswerIn(BaseModel):
    question_id: int = Field(gt=0)
    answer: str = Field(min_length=1, max_length=500)


class CourseReviewAttemptIn(BaseModel):
    idempotency_key: UUID
    content_version: int = Field(gt=0)
    answers: list[CourseReviewAnswerIn] = Field(min_length=1, max_length=30)

    @field_validator("answers")
    @classmethod
    def unique_questions(
        cls, value: list[CourseReviewAnswerIn]
    ) -> list[CourseReviewAnswerIn]:
        ids = [answer.question_id for answer in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Cada questão deve ter apenas uma resposta.")
        return value


class CourseReviewQuestionResultOut(BaseModel):
    question_id: int
    position: int
    correct: bool
    answer: str
    accepted_answers: list[str]
    explanation: str
    lesson_numbers: list[int]


class CourseReviewAttemptOut(BaseModel):
    id: int
    content_version: int
    score: int
    total: int
    score_percent: int
    status: Literal["consolidated", "reinforce"]
    reinforced_lesson_numbers: list[int]
    feedback: list[CourseReviewQuestionResultOut]
    completed_at: datetime


class CourseReviewDetailOut(CourseReviewSummaryOut):
    source_title: str
    source_url: str | None
    source_note: str
    intro: str
    content_version: int
    listening_media: LessonMediaOut | None
    listening_source_page_url: str | None
    questions: list[CourseReviewQuestionOut]
    latest_attempt: CourseReviewAttemptOut | None
