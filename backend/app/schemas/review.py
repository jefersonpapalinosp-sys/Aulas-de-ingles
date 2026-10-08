"""Contratos da fila de revisão multimodal."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ReviewItemType = Literal[
    "vocabulary",
    "grammar_error",
    "phrase",
    "listening",
    "writing_prompt",
    "speaking_prompt",
]
ReviewItemStatus = Literal["active", "suspended"]


class CardOut(BaseModel):
    """Frente, verso, mídia e estado de um item da fila."""

    id: int
    item_type: ReviewItemType
    skill: str
    prompt: str
    prompt_note: str | None
    answer: str
    context: str | None
    lesson_number: int
    reason: str
    estimated_seconds: int
    media_url: str | None
    cue_start_seconds: float | None
    cue_end_seconds: float | None
    status: ReviewItemStatus
    vocab_item_id: int | None

    ease_factor: float
    interval_days: int
    repetitions: int
    lapses: int
    due_at: datetime


class GradeIn(BaseModel):
    quality: int = Field(
        ge=0, le=5, description="0-2 errou · 3 acertou com dificuldade · 4 acertou · 5 fácil"
    )


class GradeOut(BaseModel):
    id: int
    interval_days: int
    ease_factor: float
    repetitions: int
    lapses: int
    due_at: datetime


class ReviewItemStatusIn(BaseModel):
    status: ReviewItemStatus


class DeckSummaryOut(BaseModel):
    due_now: int
    total_cards: int
    suspended: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    added: int = Field(default=0, description="Quantos itens a última ação criou.")
