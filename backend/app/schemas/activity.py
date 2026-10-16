"""Eventos mínimos: sem teclas, texto, URLs ou identidade física do dispositivo."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ActivitySessionIn(BaseModel):
    session_id: UUID
    lesson_id: int = Field(gt=0)


class ActivitySessionOut(BaseModel):
    session_id: str
    started_at: datetime
    server_now: datetime
    max_offset_ms: int = 86_400_000
    replay_days: int = 7


class ActivityEventIn(BaseModel):
    session_id: UUID
    operation_key: UUID
    end_offset_ms: int = Field(ge=1, le=86_400_000)
    duration_ms: int = Field(ge=1, le=30_000)


class ActivityEventOut(BaseModel):
    operation_key: str
    credited_ms: int
