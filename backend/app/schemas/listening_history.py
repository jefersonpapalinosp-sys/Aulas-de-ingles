"""Retomada e histórico pessoal, independentes do currículo VOA."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.progress import MediaPositionIn


class NativePositionIn(MediaPositionIn):
    """Mesmo protocolo de sincronização do player; identidade é uma sessão nativa."""

    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0, le=2_147_483_646)


class NativePositionOut(BaseModel):
    session_id: int
    position_seconds: float
    revision: int
    completed: bool
    operation_key: str | None
    changed_at: datetime | None
    updated_at: datetime | None


class NativeHistoryItem(BaseModel):
    session_id: int
    slug: str
    version: int
    title: str
    available: bool
    started_at: datetime
    last_response_at: datetime | None
    completed: bool
    first_score: int
    latest_score: int
    answered: int
    total: int
    support_revealed: bool
    position_seconds: float


class NativeHistoryOut(BaseModel):
    items: list[NativeHistoryItem]
    next_before: int | None
    attempts: int
    first_attempt_at: datetime | None
    last_attempt_at: datetime | None
