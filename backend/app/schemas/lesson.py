"""Schemas de resposta da API.

Todo campo de texto vem em subconjunto de Markdown (ver app/db/models.py).
O cliente é quem decide como renderizar.
"""

from datetime import date, datetime
from typing import Any, Literal

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


class TranscriptCueOut(ORMModel):
    id: int
    position: int
    start_seconds: float
    end_seconds: float
    speaker: str
    text_en: str
    text_pt: str


class TranscriptLineOut(BaseModel):
    position: int
    speaker: str
    text_en: str


class LessonMediaOut(ORMModel):
    id: int
    kind: str
    label: str
    source_url: str
    license_status: Literal[
        "public_domain", "permission_granted", "restricted", "review_required"
    ]
    license_url: str | None
    license_note: str
    attribution: str
    offline_policy: Literal["network_only", "cache_allowed"]
    license_reviewed_at: date | None
    duration_seconds: int | None
    listening_exercise_position: int | None
    cues: list[TranscriptCueOut]
    transcript: list[TranscriptLineOut]


class ContentSourceOut(ORMModel):
    kind: Literal["official", "authorial"]
    title: str
    publisher: str
    url: str | None
    license_note: str
    accessed_at: date


class LessonVersionOut(ORMModel):
    version: int
    status: Literal["draft", "reviewed", "published"]
    learning_strategy: str
    review_note: str
    reviewed_at: datetime
    published_at: datetime | None


class WritingRequirementOut(BaseModel):
    label: str
    terms: list[str]


class WritingPromptOut(ORMModel):
    id: int
    position: int
    title: str
    instructions: str
    min_words: int
    min_sentences: int
    requirements: list[WritingRequirementOut]


class ExerciseOut(ORMModel):
    """Exercício como ele chega ao cliente.

    A resposta certa **não** faz parte deste schema. Dica e explicação mantêm
    as chaves legadas, mas chegam nulas na leitura inicial; o servidor só as
    libera pelos fluxos autenticados de tentativa, dica ou revelação.
    """

    id: int
    position: int
    activity_type: str
    skill: str
    objective: Literal["recognize", "apply", "correct", "produce", "listen"]
    options: list[str] | None
    prompt: str
    hint: str | None
    hint_count: int
    explanation: str | None


class ExerciseWithLessonOut(ExerciseOut):
    course_slug: str
    unit_slug: str
    lesson_number: int


class CourseSummaryOut(ORMModel):
    id: int
    slug: str
    title: str
    level: str
    proficiency_label: str
    provider: str
    source_url: str
    position: int
    status: Literal["planned", "published", "archived"]
    total_lessons: int
    published_lessons: int


class LessonSummaryOut(ORMModel):
    """O que a trilha de navegação precisa — sem carregar a aula inteira."""

    id: int
    course_slug: str
    unit_slug: str
    slug: str
    position: int
    number: int
    title: str
    title_pt: str
    grammar_tag: str
    focus_points: list[str]
    story_note: str | None


class CourseReviewSummaryOut(ORMModel):
    """Checkpoint como item curricular próprio, sem fingir ser uma aula."""

    id: int
    slug: str
    title: str
    position: int
    status: Literal["planned", "published", "archived"]
    source_kind: Literal["official", "authorial", "mixed"]
    estimated_minutes: int
    review_lesson_number: int
    question_count: int


class CourseUnitOut(ORMModel):
    id: int
    slug: str
    title: str
    position: int
    status: Literal["planned", "published", "archived"]
    lesson_start: int
    lesson_end: int
    total_lessons: int
    published_lessons: int
    lessons: list[LessonSummaryOut]
    review: CourseReviewSummaryOut | None


class CourseCurriculumOut(BaseModel):
    course: CourseSummaryOut
    units: list[CourseUnitOut]


class LessonDetailOut(LessonSummaryOut):
    voa_url: str
    lead: str
    warmup_prompt: str
    listening_focus: str
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
    media: list[LessonMediaOut]
    content_sources: list[ContentSourceOut]
    versions: list[LessonVersionOut]
    writing_prompts: list[WritingPromptOut]
    exercises: list[ExerciseOut]

    @field_validator("exercises", mode="before")
    @classmethod
    def _ocultar_feedback_inicial(cls, value: Any) -> Any:
        """Dicas e explicação só saem pelos endpoints autenticados de feedback."""
        if not isinstance(value, list):
            return value
        return [exercise_public_payload(item) for item in value]


def exercise_public_payload(exercise: Any) -> dict[str, Any]:
    """Serializa um exercício sem gabarito, dica ou explicação antecipada."""
    return {
        "id": exercise.id,
        "position": exercise.position,
        "activity_type": exercise.activity_type,
        "skill": exercise.skill,
        "objective": exercise.objective,
        "options": exercise.options,
        "prompt": exercise.prompt,
        "hint": None,
        "hint_count": exercise.hint_count,
        "explanation": None,
    }
