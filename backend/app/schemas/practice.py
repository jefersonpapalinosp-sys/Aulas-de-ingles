"""Contratos do laboratório de exercícios e da retomada sincronizada."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.lesson import ExerciseOut
from app.schemas.progress import AttemptFeedbackOut, ExerciseHintOut

PracticeMode = Literal["guided", "quick", "mistakes"]
PracticeStatus = Literal["active", "completed", "abandoned"]
ExerciseActivityType = Literal[
    "gap_fill", "multiple_choice", "transformation", "reorder", "dictation"
]
ExerciseSkill = Literal["grammar", "listening"]
ExerciseObjective = Literal["recognize", "apply", "correct", "produce", "listen"]
PracticeOutcome = Literal["pending", "first_try_correct", "corrected", "revealed"]


class PracticeSessionCreateIn(BaseModel):
    idempotency_key: UUID
    mode: PracticeMode = "guided"
    activity_type: ExerciseActivityType | None = None
    skill: ExerciseSkill | None = None
    objective: ExerciseObjective | None = None
    source_session_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validar_sessao_de_origem(self) -> Self:
        if self.mode == "mistakes" and self.source_session_id is None:
            raise ValueError("O modo mistakes exige source_session_id.")
        if self.mode != "mistakes" and self.source_session_id is not None:
            raise ValueError("source_session_id só pode ser usado no modo mistakes.")
        return self


class PracticePositionIn(BaseModel):
    current_position: int = Field(ge=0)
    expected_revision: int = Field(gt=0)
    idempotency_key: UUID


class PracticeSummaryOut(BaseModel):
    total: int
    completed: int
    first_try_correct: int
    corrected: int
    revealed: int
    pending: int


class PracticeSessionItemOut(BaseModel):
    position: int
    exercise: ExerciseOut
    attempt_count: int
    first_try_correct: bool | None
    highest_hint_level: int
    opened_hints: list[ExerciseHintOut]
    answer_revealed: bool
    completed_at: datetime | None
    outcome: PracticeOutcome
    last_feedback: AttemptFeedbackOut | None
    answers: list[str] | None
    explanation: str | None


class PracticeSessionOut(BaseModel):
    id: int
    course_slug: str
    unit_slug: str
    lesson_number: int
    lesson_title: str
    content_version: int
    mode: PracticeMode
    status: PracticeStatus
    activity_type: str | None
    skill: str | None
    objective: ExerciseObjective | None
    content_changed: bool
    current_position: int
    state_revision: int
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    summary: PracticeSummaryOut
    items: list[PracticeSessionItemOut]


class PracticeHintOut(ExerciseHintOut):
    item: PracticeSessionItemOut


class PracticeRevealOut(BaseModel):
    answers: list[str]
    explanation: str
    item: PracticeSessionItemOut
