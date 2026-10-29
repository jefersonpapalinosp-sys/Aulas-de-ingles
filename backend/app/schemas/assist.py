"""Contratos dos recursos assistidos experimentais."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import HumanRating, TranscriptionStatus, WorkerState


class HumanRatingIn(BaseModel):
    rating: HumanRating


class TranscriptionWordOut(BaseModel):
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float | None = Field(ge=0, le=1)


class TranscriptionJobOut(BaseModel):
    id: int
    attempt_id: int
    status: TranscriptionStatus
    provider: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    automated: Literal[True] = True
    evaluation_only: Literal[True] = True
    expected_text: str | None
    historical_content_status: Literal["available", "unavailable"]
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
    reserved_today: int
    consumed_today: int
    quota_resets_at: datetime
    quota_timezone: Literal["UTC"] = "UTC"
    retention_days: int
    cost_microusd_today: int
    cost_incomplete: bool
    worker_state: WorkerState = "unknown"
    worker_seen_at: datetime | None = None
    queued_jobs: int = 0
    oldest_queued_seconds: int | None = None
