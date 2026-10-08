"""Schemas de progresso e tentativas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

StudyStep = Literal["preparar", "assistir", "estudar", "praticar", "revisar"]
STUDY_STEPS: tuple[StudyStep, ...] = (
    "preparar",
    "assistir",
    "estudar",
    "praticar",
    "revisar",
)


class AttemptIn(BaseModel):
    answer: str = Field(max_length=200, description="O que o usuário digitou.")
    idempotency_key: UUID


class FeedbackTokenOut(BaseModel):
    text: str
    status: Literal["keep", "review"]


class AttemptFeedbackOut(BaseModel):
    category: Literal[
        "correct", "missing_word", "extra_word", "word_order", "spelling", "word_choice"
    ]
    message: str
    tokens: list[FeedbackTokenOut]


class AttemptOut(BaseModel):
    attempt_id: int
    correct: bool
    explanation: str | None
    feedback: AttemptFeedbackOut


class ExerciseHintOut(BaseModel):
    level: int
    content: str


class RevealAnswerOut(BaseModel):
    """Só sai quando o usuário pede explicitamente para ver a resposta."""

    answers: list[str]
    explanation: str


class LessonProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lesson_number: int
    studied: bool
    studied_at: datetime | None
    attempts: int
    correct: int


class ProgressOut(BaseModel):
    studied_count: int
    total_lessons: int
    attempts: int
    correct: int
    review_due: int = Field(default=0, description="Cartas vencidas agora.")
    review_cards: int = Field(default=0, description="Total de cartas no deck.")
    lessons: list[LessonProgressOut]


class StudySessionIn(BaseModel):
    current_step: StudyStep
    completed_steps: list[StudyStep] = Field(max_length=5)

    @field_validator("completed_steps")
    @classmethod
    def ordenar_sem_duplicar(cls, value: list[StudyStep]) -> list[StudyStep]:
        presentes = set(value)
        return [step for step in STUDY_STEPS if step in presentes]


class StudySessionOut(StudySessionIn):
    lesson_number: int
    started_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    total_seconds: int


class MediaPositionIn(BaseModel):
    position_seconds: float = Field(ge=0)


class MediaPositionOut(MediaPositionIn):
    media_id: int
    updated_at: datetime | None
