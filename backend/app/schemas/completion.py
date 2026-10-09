"""Resumo autenticado de conclusão de um curso."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.dashboard import SkillSummaryOut


class CompletionCourseOut(BaseModel):
    slug: str
    title: str
    level: str
    proficiency_label: str


class CourseCompletionProgressOut(BaseModel):
    published_lessons: int
    viewed_lessons: int
    completed_lessons: int
    completion_percent: int
    status: Literal["not_started", "in_progress", "completed"]


class IncompleteUnitOut(BaseModel):
    slug: str
    title: str
    published_lessons: int
    viewed_lessons: int
    completed_lessons: int
    href: str


class PendingCheckpointOut(BaseModel):
    unit_slug: str
    title: str
    content_version: int
    href: str


class CheckpointCompletionOut(BaseModel):
    published: int
    current_completed: int
    pending: list[PendingCheckpointOut]


class CertificateEligibilityOut(BaseModel):
    eligible: bool
    status: Literal["eligible", "ineligible"]
    reason: str
    required_lessons: int
    required_checkpoints: int
    scope_label: str
    cta_label: str
    cta_href: str
    automatic_download: Literal[False] = False


class CourseDiagnosticOut(BaseModel):
    title: str
    description: str
    href: str


class NextCourseOut(BaseModel):
    slug: str
    title: str
    level: str
    proficiency_label: str
    status: Literal["planned", "published", "archived"]
    recommended: Literal[True] = True
    required: Literal[False] = False
    href: str
    preview: str
    diagnostic: CourseDiagnosticOut


class CourseCompletionOut(BaseModel):
    course: CompletionCourseOut
    progress: CourseCompletionProgressOut
    incomplete_units: list[IncompleteUnitOut]
    checkpoints: CheckpointCompletionOut
    skills: list[SkillSummaryOut]
    certificate: CertificateEligibilityOut
    next_course: NextCourseOut | None
