"""Schemas de resposta da API.

Todo campo de texto vem em subconjunto de Markdown (ver app/db/models.py).
O cliente é quem decide como renderizar.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class GrammarRowOut(ORMModel):
    cells: list[str] = Field(description="Células da linha, na ordem do table_head do bloco.")


class GrammarBlockOut(ORMModel):
    heading: str
    why: str
    warning: str | None
    table_head: list[str] | None
    rows: list[GrammarRowOut]


class PhraseOut(ORMModel):
    text_en: str
    text_pt: str
    note: str


class VocabItemOut(ORMModel):
    id: int
    term: str
    ipa: str
    translation_pt: str
    example_en: str


class VocabItemWithLessonOut(VocabItemOut):
    lesson_number: int


class PronunciationNoteOut(ORMModel):
    label: str
    explanation: str


class ExerciseOut(ORMModel):
    """Exercício como ele chega ao cliente.

    A resposta certa **não** faz parte deste schema. Na S3 a correção passa a
    ser feita pelo servidor; até lá o cliente corrige, mas o contrato já nasce
    no formato certo para não ter que mudar depois.
    """

    id: int
    position: int
    prompt: str
    hint: str | None
    explanation: str


class ExerciseWithLessonOut(ExerciseOut):
    lesson_number: int


class LessonSummaryOut(ORMModel):
    """O que a trilha de navegação precisa — sem carregar a aula inteira."""

    number: int
    title: str
    title_pt: str
    grammar_tag: str
    focus_points: list[str]
    story_note: str | None


class LessonDetailOut(LessonSummaryOut):
    voa_url: str
    lead: str
    goals: list[str]

    @field_validator("goals", mode="before")
    @classmethod
    def _apenas_o_texto(cls, valor: Any) -> Any:
        """O ORM entrega objetos LessonGoal; o contrato expõe só o texto."""
        if isinstance(valor, list):
            return [getattr(item, "text", item) for item in valor]
        return valor

    grammar_blocks: list[GrammarBlockOut]
    phrases: list[PhraseOut]
    vocab: list[VocabItemOut]
    pronunciation: list[PronunciationNoteOut]
    exercises: list[ExerciseOut]
