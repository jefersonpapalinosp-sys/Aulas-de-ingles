"""Contratos do caderno e da exportação pessoal."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

NotebookKind = Literal[
    "note",
    "favorite_phrase",
    "personal_example",
    "recurring_error",
    "teacher_question",
]


class NotebookEntryIn(BaseModel):
    lesson_number: int = Field(ge=1)
    kind: NotebookKind
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("A anotação não pode ficar vazia.")
        return content


class NotebookEntryUpdate(BaseModel):
    kind: NotebookKind
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("A anotação não pode ficar vazia.")
        return content


class NotebookEntryOut(BaseModel):
    id: int
    lesson_number: int
    lesson_title: str
    kind: NotebookKind
    content: str
    created_at: datetime
    updated_at: datetime


class PersonalDataExportOut(BaseModel):
    schema_version: str
    exported_at: datetime
    profile: dict[str, Any]
    lesson_progress: list[dict[str, Any]]
    study_sessions: list[dict[str, Any]]
    study_plan: dict[str, Any] | None
    step_progress: list[dict[str, Any]]
    media_progress: list[dict[str, Any]]
    skill_evidence: list[dict[str, Any]]
    exercise_attempts: list[dict[str, Any]]
    review_items: list[dict[str, Any]]
    writing: list[dict[str, Any]]
    speaking: list[dict[str, Any]]
    notebook: list[dict[str, Any]]
