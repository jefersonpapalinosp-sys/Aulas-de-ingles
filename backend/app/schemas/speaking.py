"""Contratos da prática oral com gravação opcional."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import IntegrityState, SelfRating, SpeakingStatus
from app.schemas.assist import TranscriptionJobOut
from app.services.audio_upload import MAX_DURATION_MS


class SpeakingAttemptIn(BaseModel):
    cue_id: int
    duration_ms: int = Field(ge=1, le=MAX_DURATION_MS)
    self_rating: SelfRating | None = None
    consent: Literal[True]


class SpeakingAttemptOut(BaseModel):
    id: int
    course_slug: str
    course_title: str
    unit_slug: str
    lesson_number: int
    cue_id: int
    cue_text: str | None
    historical_content_status: Literal["available", "unavailable"]
    duration_ms: int
    self_rating: SelfRating | None
    consented_at: datetime
    status: SpeakingStatus
    mime_type: str | None
    file_size: int | None
    created_at: datetime
    integrity_state: IntegrityState = "unknown"
    transcription: TranscriptionJobOut | None = None


class SpeakingAttemptPageOut(BaseModel):
    items: list[SpeakingAttemptOut]
    next_cursor: str | None


class SpeakingPolicyOut(BaseModel):
    max_bytes: int
    max_duration_ms: int
    mime_types: list[str]
    upload_timeout_seconds: int
    content_validation: Literal["decoded_audio_v1"] = "decoded_audio_v1"
    recording_target_ms: int = 29_000
    max_channels: int = 2
    min_sample_rate_hz: int = 8000
    max_sample_rate_hz: int = 48000
