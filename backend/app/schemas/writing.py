"""Schemas do workspace de produção escrita."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import AnalysisMode, HumanRating


class _WritingTextIn(BaseModel):
    text: str = Field(max_length=5000)


class WritingDraftIn(_WritingTextIn):
    expected_revision: int | None = Field(default=None, ge=0)


class WritingFeedbackIn(_WritingTextIn):
    """O feedback não compara revisão: o texto analisado vem no corpo.

    A `operation_key` é que importa aqui — ela governa a reserva de cota da
    assistência e, no reenvio, devolve o registro em vez de cobrar de novo.
    """

    assisted: bool = False
    operation_key: UUID | None = None


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
    historical_content_status: Literal["available", "unavailable"]
    evaluation_scope: str
    analysis_mode: AnalysisMode
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


class WritingRevisionPageOut(BaseModel):
    items: list[WritingRevisionOut]
    next_cursor: str | None


class WritingFeedbackPageOut(BaseModel):
    items: list[WritingFeedbackOut]
    next_cursor: str | None


class WritingHistorySummaryOut(BaseModel):
    prompt_id: int
    course_slug: str
    course_title: str
    unit_slug: str
    lesson_number: int
    lesson_title: str
    prompt_title: str
    updated_at: datetime
    revision_count: int
    feedback_count: int


class WritingHistoryPageOut(BaseModel):
    items: list[WritingHistorySummaryOut]
    next_cursor: str | None
