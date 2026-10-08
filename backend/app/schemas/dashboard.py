"""Contratos do painel Hoje e do plano semanal."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
RecommendationKind = Literal["review", "continue_lesson", "start_lesson", "practice"]


class StudyPlanIn(BaseModel):
    weekly_minutes: int = Field(ge=30, le=600)
    preferred_days: list[Weekday] = Field(min_length=1, max_length=7)
    goal: str = Field(min_length=1, max_length=200)

    @field_validator("preferred_days")
    @classmethod
    def unique_days(cls, value: list[Weekday]) -> list[Weekday]:
        if len(set(value)) != len(value):
            raise ValueError("Os dias preferidos não podem se repetir.")
        order: tuple[Weekday, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        selected = set(value)
        return [day for day in order if day in selected]

    @field_validator("goal")
    @classmethod
    def goal_not_blank(cls, value: str) -> str:
        goal = value.strip()
        if not goal:
            raise ValueError("A meta não pode ficar vazia.")
        return goal


class StudyPlanOut(StudyPlanIn):
    updated_at: datetime | None


class RecommendationOut(BaseModel):
    kind: RecommendationKind
    title: str
    reason: str
    href: str
    estimated_minutes: int
    lesson_number: int | None = None


class RecentSessionOut(BaseModel):
    lesson_number: int
    lesson_title: str
    current_step: str
    completed_steps: int
    total_minutes: int
    updated_at: datetime


class TodayOut(BaseModel):
    recommendation: RecommendationOut
    plan: StudyPlanOut
    recorded_minutes_this_week: int
    recent_session: RecentSessionOut | None


class SkillSummaryOut(BaseModel):
    skill: str
    label: str
    samples: int
    score_percent: int | None
    status: Literal["insufficient", "developing", "steady", "strong"]
    fragile_topics: list[str]
