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
    course_slug: str = Field(default="voa-level-1", min_length=1, max_length=100)
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
    course_slug: str
    course_title: str
    unit_slug: str
    lesson_number: int
    lesson_title: str
    kind: NotebookKind
    content: str
    created_at: datetime
    updated_at: datetime


class NotebookPageOut(BaseModel):
    items: list[NotebookEntryOut]
    next_cursor: str | None


class AudioExportEntry(BaseModel):
    attempt_id: int
    mime_type: str | None
    file_size: int | None
    sha256: str | None
    integrity_state: Literal["unknown", "verified", "missing", "changed"]
    download_path: str | None


class ExportScope(BaseModel):
    snapshot_at: datetime
    isolation: Literal["repeatable_read"] = "repeatable_read"
    includes_audio_bytes: Literal[False] = False
    is_account_backup: Literal[False] = False
    stored_on_server: Literal[False] = False
    row_counts: dict[str, int]
    exclusions: list[str]
    historical_content_note: str
    audio_access_note: str
    max_records: int
    max_json_bytes: int


class PersonalDataExportOut(BaseModel):
    schema_version: str
    exported_at: datetime
    profile: dict[str, Any]
    lesson_progress: list[dict[str, Any]]
    study_sessions: list[dict[str, Any]]
    study_plan: dict[str, Any] | None
    step_progress: list[dict[str, Any]]
    media_progress: list[dict[str, Any]]
    activity_sessions: list[dict[str, Any]]
    activity_events: list[dict[str, Any]]
    active_intervals: list[dict[str, Any]]
    skill_evidence: list[dict[str, Any]]
    exercise_attempts: list[dict[str, Any]]
    review_items: list[dict[str, Any]]
    writing: list[dict[str, Any]]
    speaking: list[dict[str, Any]]
    notebook: list[dict[str, Any]]
    scope: ExportScope | None = None
    checkpoint_attempts: list[dict[str, Any]] = Field(default_factory=list)
    practice_sessions: list[dict[str, Any]] = Field(default_factory=list)
    practice_items: list[dict[str, Any]] = Field(default_factory=list)
    writing_feedback: list[dict[str, Any]] = Field(default_factory=list)
    review_events: list[dict[str, Any]] = Field(default_factory=list)
    legacy_review_cards: list[dict[str, Any]] = Field(default_factory=list)
    assistance_usage: list[dict[str, Any]] = Field(default_factory=list)
    login_sessions: list[dict[str, Any]] = Field(default_factory=list)
    audio_manifest: list[AudioExportEntry] = Field(default_factory=list)
    content_snapshots: list[dict[str, Any]] = Field(default_factory=list)
