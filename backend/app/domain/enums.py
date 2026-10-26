"""Conjuntos fechados que o banco, os modelos e os contratos compartilham.

Cada alias aqui tem uma ``CheckConstraint`` equivalente em
:mod:`app.db.models`: o banco recusa valor fora do conjunto e o mypy recusa
código que escreva ou leia outro. Antes disso as colunas eram ``Mapped[str]`` e
cada passagem para o schema exigia ``type: ignore[arg-type]`` — dezessete delas,
todas com esta mesma causa.

O módulo não importa nada do projeto de propósito: ``app.db`` e ``app.schemas``
dependem dele, nunca o contrário. Mudar um conjunto aqui exige migration quando
houver ``CheckConstraint`` correspondente.
"""

from typing import Literal

# Catálogo e publicação
PublicationStatus = Literal["planned", "published", "archived"]

# Prática oral
SelfRating = Literal["repeat", "almost", "confident"]
# De onde veio o áudio: linha de transcrição (shadowing) ou turno de diálogo
# (Guiado). O BE-46 tornou `transcript_cue_id` opcional e este conjunto é o que
# mantém a garantia: shadowing sem cue continua impossível.
AudioOrigin = Literal["cue", "dialogue"]
SpeakingStatus = Literal["pending", "ready"]
IntegrityState = Literal["unknown", "verified", "missing", "changed"]

# Assistência
HumanRating = Literal["helpful", "not_helpful"]
TranscriptionStatus = Literal["queued", "processing", "completed", "failed"]
# O que o worker faz com o job: transcrever áudio ou conduzir um turno de
# diálogo (que pode ser de texto, sem áudio nenhum).
JobKind = Literal["transcription", "dialogue"]
WorkerState = Literal["disabled", "unknown", "active", "stale"]
AnalysisMode = Literal["deterministic", "assisted", "fallback"]
AssistModality = Literal["transcription", "writing"]

# Laboratório de exercícios
PracticeMode = Literal["guided", "quick", "mistakes"]
PracticeStatus = Literal["active", "completed", "abandoned"]
PracticeOutcome = Literal["pending", "first_try_correct", "corrected", "revealed"]
ExerciseObjective = Literal["recognize", "apply", "correct", "produce", "listen"]

# Caderno
NotebookKind = Literal[
    "note",
    "favorite_phrase",
    "personal_example",
    "recurring_error",
    "teacher_question",
]

# Exclusão de conta: o job admite ``failed``; a resposta da requisição, não —
# um job recém-criado nunca nasce falho.
DeletionJobState = Literal["cleanup_pending", "completed", "failed"]
DeletionResultState = Literal["cleanup_pending", "completed"]
