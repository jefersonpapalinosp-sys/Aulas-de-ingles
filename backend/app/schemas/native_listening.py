"""Conteúdo editorial privado e projeções seguras para o aluno."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NativeOption(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    label: str = Field(min_length=1, max_length=200)


class NativeConfigOut(StrictModel):
    enabled: bool
    preview: bool


class NativeQuestion(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    prompt: str = Field(min_length=1, max_length=400)
    kind: Literal["single_choice", "multi_select"]
    selection_count: int = Field(ge=1, le=2)
    options: list[NativeOption] = Field(min_length=2, max_length=6)


class EditorialQuestion(NativeQuestion):
    answer_ids: list[str]
    explanation: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def valid_answers(self) -> "EditorialQuestion":
        ids = {option.id for option in self.options}
        if len(ids) != len(self.options):
            raise ValueError("Opções repetidas.")
        expected = 1 if self.kind == "single_choice" else 2
        if self.selection_count != expected or len(self.answer_ids) != expected:
            raise ValueError("Quantidade de respostas incompatível.")
        if len(set(self.answer_ids)) != expected or not set(self.answer_ids) <= ids:
            raise ValueError("Gabarito inválido.")
        return self


class NativeContent(StrictModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    topic: str = Field(min_length=1, max_length=50)
    level: Literal["A2"]
    status: Literal["draft", "published", "archived"]
    instructions: str = Field(min_length=1, max_length=600)
    transcript: str = Field(min_length=1, max_length=6000)
    map_rows: list[list[str]] = Field(default_factory=list, max_length=8)
    map_description: str | None = Field(default=None, max_length=1000)
    questions: list[EditorialQuestion] = Field(min_length=3, max_length=7)
    audio_file: str = Field(pattern=r"^[a-z0-9-]+-v[1-9][0-9]*\.mp3$")
    audio_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    audio_duration_seconds: float = Field(gt=0, le=600)
    attribution: str = Field(min_length=1, max_length=500)
    rights_note: str = Field(min_length=1, max_length=1000)
    audio_provenance: str = Field(min_length=1, max_length=1000)
    reviewed_by: str | None = None
    reviewed_on: str | None = None
    rights_approved: bool = False

    @model_validator(mode="after")
    def valid_content(self) -> "NativeContent":
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Questões repetidas.")
        if self.map_rows and (
            not self.map_description or any(not row or len(row) > 8 for row in self.map_rows)
        ):
            raise ValueError("Mapa exige alternativa acessível.")
        if self.status == "published" and not (
            self.reviewed_by and self.reviewed_on and self.rights_approved
        ):
            raise ValueError("Publicação exige revisão editorial e de direitos.")
        return self


class NativeActivityOut(StrictModel):
    slug: str
    version: int
    title: str
    topic: str
    level: str
    preview: bool
    instructions: str
    questions: list[NativeQuestion]
    map_rows: list[list[str]]
    map_description: str | None
    audio_duration_seconds: float
    attribution: str
    rights_note: str


class NativeStartIn(StrictModel):
    version: int = Field(ge=1)
    operation_key: UUID


class NativeResponseIn(StrictModel):
    kind: Literal["answer", "reveal", "transcript"]
    question_id: str | None = Field(default=None, max_length=40)
    selected_ids: list[str] = Field(default_factory=list, max_length=6)
    expected_revision: int = Field(ge=0, le=100)
    operation_key: UUID

    @model_validator(mode="after")
    def valid_response(self) -> "NativeResponseIn":
        if len(set(self.selected_ids)) != len(self.selected_ids):
            raise ValueError("Opções duplicadas.")
        if (self.kind == "transcript") != (self.question_id is None):
            raise ValueError("Questão incompatível com a ação.")
        if self.kind != "answer" and self.selected_ids:
            raise ValueError("Revelação não recebe respostas.")
        return self


class NativeFeedbackOut(StrictModel):
    question_id: str
    kind: str
    selected_ids: list[str]
    correct: bool
    first_response: bool
    answer_ids: list[str]
    explanation: str


class NativeSessionOut(StrictModel):
    id: int
    activity: NativeActivityOut
    revision: int
    completed: bool
    score: int
    total: int
    support_revealed: bool
    transcript: str | None
    feedback: list[NativeFeedbackOut]
    created_at: datetime
