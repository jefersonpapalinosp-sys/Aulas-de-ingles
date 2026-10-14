"""Schemas do workspace de produção escrita."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.assist import HumanRating


class WritingDraftIn(BaseModel):
    text: str = Field(max_length=5000)
    expected_revision: int | None = Field(default=None, ge=0)


class WritingFeedbackIn(WritingDraftIn):
    assisted: bool = False


class WritingRevisionOut(BaseModel):
    id: int
    version: int
    text: str
    created_at: datetime
    draft_revision: int = 0


class WritingDraftOut(BaseModel):
    revision: int = 0
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
    source_text_hash: str
    id: int
    word_count: int
    sentence_count: int
    ready: bool
    checks: list[WritingFeedbackCheckOut]
    algorithm_version: str
    rubric_version: str | None
    rubric_snapshot: dict[str, object] | None
    evaluation_scope: str
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
