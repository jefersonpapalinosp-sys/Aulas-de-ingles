"""Schemas do deck de revisão."""

from datetime import datetime

from pydantic import BaseModel, Field


class CardOut(BaseModel):
    """Frente e verso da carta, mais o estado do agendamento."""

    id: int
    vocab_item_id: int
    term: str
    ipa: str
    translation_pt: str
    example_en: str
    lesson_number: int

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


class DeckSummaryOut(BaseModel):
    due_now: int
    total_cards: int
    added: int = Field(default=0, description="Quantas cartas a última ação criou.")
