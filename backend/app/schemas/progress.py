"""Schemas de progresso e tentativas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AttemptIn(BaseModel):
    answer: str = Field(max_length=200, description="O que o usuário digitou.")


class AttemptOut(BaseModel):
    correct: bool
    explanation: str


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
    lessons: list[LessonProgressOut]
