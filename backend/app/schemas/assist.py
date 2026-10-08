"""Contratos dos recursos assistidos experimentais."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

HumanRating = Literal["helpful", "not_helpful"]


class HumanRatingIn(BaseModel):
    rating: HumanRating


class TranscriptionWordOut(BaseModel):
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class TranscriptionJobOut(BaseModel):
    id: int
    attempt_id: int
    status: Literal["queued", "processing", "completed", "failed"]
    provider: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    automated: Literal[True] = True
    evaluation_only: Literal[True] = True
    expected_text: str
    transcript_text: str | None
    words: list[TranscriptionWordOut]
    mean_confidence: float | None
    similarity_score: float | None
    low_confidence: bool
    error_code: str | None
    cost_microusd: int
    human_rating: HumanRating | None
    requested_at: datetime
    completed_at: datetime | None
    expires_at: datetime


class AssistStatusOut(BaseModel):
    transcription_enabled: bool
    writing_enabled: bool
    evaluation_only: Literal[True] = True
    daily_quota: int
    used_today: int
    remaining_today: int
    retention_days: int
    cost_microusd_today: int
