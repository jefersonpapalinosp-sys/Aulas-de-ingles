"""Contratos do parceiro de conversa (IA-45/BE-46).

O que sai daqui para o cliente é o resultado determinístico mais o texto do
parceiro. `checks` é um mapa código→booleano, não nota: o aluno vê o que
cumpriu, nunca um percentual inventado. `fallback` diz que a resposta veio do
roteiro da aula, e não do modelo — a interface precisa poder contar isso em vez
de fingir que o parceiro respondeu.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.dialogue import CheckCode
from app.domain.enums import (
    DialogueMode,
    DialogueState,
    HumanRating,
    TurnInputKind,
    TurnRole,
    TurnState,
)
from app.schemas.assist import TranscriptionWordOut


class DialogueCreateIn(BaseModel):
    lesson_id: int
    mode: DialogueMode = "script"
    partner_speaker: str | None = Field(default=None, max_length=80)
    # Idempotência da criação: reenviar abre o mesmo diálogo.
    operation_key: UUID | None = None


class TurnTextIn(BaseModel):
    text: str = Field(max_length=2000)
    idempotency_key: UUID | None = None


class DialogueHintOut(BaseModel):
    code: CheckCode
    message: str


class DialogueTermCheck(BaseModel):
    text: str
    covered: bool


class DialogueCheckDetails(BaseModel):
    target_terms: list[DialogueTermCheck]
    grammar_patterns: list[DialogueTermCheck]


class DialogueTurnOut(BaseModel):
    position: int
    role: TurnRole
    input_kind: TurnInputKind | None
    state: TurnState
    transcript: str | None
    # Mapa código→cumpriu. Sem nota, sem percentual: é o contrato do ADR.
    checks: dict[str, bool]
    check_details: DialogueCheckDetails | None = None
    partner_text: str | None
    hints: list[DialogueHintOut]
    confidence: float | None
    fallback: bool
    error_code: str | None
    human_rating: HumanRating | None
    job_id: int | None
    created_at: datetime
    completed_at: datetime | None
    words: list[TranscriptionWordOut] = Field(default_factory=list)


class DialogueStatusOut(BaseModel):
    enabled: bool
    guided_enabled: bool
    audio_enabled: bool
    daily_quota: int
    remaining_today: int
    reserved_today: int
    consumed_today: int
    quota_resets_at: datetime
    retention_days: int
    cost_microusd_today: int
    cost_incomplete: bool


class DialogueSummaryOut(BaseModel):
    id: int
    lesson_id: int
    mode: DialogueMode
    state: DialogueState
    partner_speaker: str | None
    turn_limit: int
    # Quantos turnos do aluno ainda cabem neste diálogo, já descontado o que
    # existe: evita o cliente recontar e divergir.
    turns_remaining: int
    provider_name: str | None
    rubric_version: str
    started_at: datetime
    ended_at: datetime | None


class DialogueOut(DialogueSummaryOut):
    turns: list[DialogueTurnOut]


class DialoguePageOut(BaseModel):
    items: list[DialogueSummaryOut]
    next_cursor: str | None


class DialogueTurnAcceptedOut(BaseModel):
    """Resposta do turno admitido.

    `job_id` é nulo no Roteiro, que não passa pela fila — ele não chama
    provedor nenhum e não pode depender do worker estar de pé.
    """

    position: int
    state: TurnState
    job_id: int | None
    turns_remaining: int
