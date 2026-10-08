"""Contratos da prática oral com gravação opcional."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.assist import TranscriptionJobOut

SelfRating = Literal["repeat", "almost", "confident"]


class SpeakingAttemptIn(BaseModel):
    cue_id: int
    duration_ms: int = Field(ge=1, le=30_000)
    self_rating: SelfRating | None = None
    consent: Literal[True]


class SpeakingAttemptOut(BaseModel):
    id: int
    course_slug: str
    course_title: str
    unit_slug: str
    lesson_number: int
    cue_id: int
    cue_text: str
    duration_ms: int
    self_rating: SelfRating | None
    consented_at: datetime
    status: Literal["pending", "ready"]
    mime_type: str | None
    file_size: int | None
    created_at: datetime
    transcription: TranscriptionJobOut | None = None
