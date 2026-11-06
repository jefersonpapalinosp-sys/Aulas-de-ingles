"""Catálogo externo e progresso explicitamente autodeclarado."""

from datetime import date, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ListeningState = Literal["not_started", "in_progress", "completed"]


class ListeningConfigOut(BaseModel):
    enabled: bool


class ListeningResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=300)
    topic: str = Field(min_length=1, max_length=50)
    level: Literal["A2"]
    source: Literal["Test-English"]
    source_url: str = Field(max_length=400)
    mode: Literal["external_link"]
    availability: Literal["available", "unavailable"]
    checked_on: date
    version: int = Field(ge=1)
    position: int = Field(ge=1)

    @field_validator("source_url")
    @classmethod
    def safe_source(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or url.netloc != "test-english.com"
            or not url.path.startswith("/listening/a2/")
            or url.path == "/listening/a2/"
            or not url.path.endswith("/")
            or url.query
            or url.fragment
        ):
            raise ValueError("A origem precisa ser uma atividade A2 do Test-English.")
        return value


class ListeningProgressIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: ListeningState
    expected_revision: int = Field(ge=0, le=2_147_483_646)
    operation_key: UUID


class ListeningProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    resource_slug: str
    state: ListeningState
    revision: int
    updated_at: datetime
