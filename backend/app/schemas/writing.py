"""Schemas do workspace de produção escrita."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.assist import HumanRating


class WritingDraftIn(BaseModel):
    text: str = Field(max_length=5000)


class WritingFeedbackIn(WritingDraftIn):
    assisted: bool = False


class WritingRevisionOut(BaseModel):
    id: int
    version: int
    text: str
    created_at: datetime


class WritingDraftOut(BaseModel):
    prompt_id: int
    text: str
    updated_at: datetime | None
    revisions: list[WritingRevisionOut]


class WritingFeedbackCheckOut(BaseModel):
    code: str
    label: str
    passed: bool
    suggestion: str


class WritingFeedbackOut(BaseModel):
    id: int
    word_count: int
    sentence_count: int
    ready: bool
    checks: list[WritingFeedbackCheckOut]
    analysis_mode: Literal["deterministic", "assisted", "fallback"]
    automated: Literal[True] = True
    evaluation_only: bool
    provider: str | None
    assisted_summary: str | None
    assisted_suggestions: list[dict[str, object]]
    assisted_confidence: float | None
    low_confidence: bool
    assisted_cost_microusd: int
    assisted_error_code: str | None
    human_rating: HumanRating | None
    created_at: datetime


class WritingHistoryItemOut(BaseModel):
    prompt_id: int
    course_slug: str
    course_title: str
    unit_slug: str
    lesson_number: int
    lesson_title: str
    prompt_title: str
    draft_text: str
    updated_at: datetime
    revisions: list[WritingRevisionOut]
    feedbacks: list[WritingFeedbackOut]
