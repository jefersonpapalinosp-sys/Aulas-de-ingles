"""Prompt, esquema e saneamento do parceiro de conversa (IA-45).

Módulo puro: só stdlib. Ele não fala com banco, provedor ou HTTP. Quem o usa
(BE-46) monta o `LessonBrief` a partir do conteúdo da aula, decide os códigos
reprovados pela camada determinística e passa a resposta bruta do provedor por
`sanitize_provider_output` antes de persistir qualquer coisa.

Regras que este módulo garante por construção:

- o payload ao provedor leva só conteúdo da aula, o texto do turno atual, os
  últimos turnos em texto e os códigos reprovados; não existe parâmetro para
  nome, e-mail ou identificador do aluno;
- o JSON Schema restringe `hints[].code` exatamente aos códigos reprovados;
- a saída é saneada: códigos não permitidos são descartados, URLs e e-mails
  invalidam o turno, texto longo demais invalida o turno.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.domain.dialogue import (
    CHECK_CODES,
    MAX_TURNS_PER_DIALOGUE,
    MAX_WORDS,
    MIN_WORDS,
    CheckCode,
)

PROMPT_VERSION = "dialogue-prompt-v1"
Mode = Literal["script", "guided", "free_unit"]
# Os códigos vêm do domínio, que é quem os produz: duas listas iguais em
# arquivos diferentes divergem na primeira vez que uma regra muda.
__all__ = ["CHECK_CODES", "MAX_TURNS_PER_DIALOGUE", "CheckCode"]

MAX_PARTNER_CHARS = 280
MAX_HINT_CHARS = 200
MAX_HINTS = 3
MAX_HISTORY_TURNS = 6
# Os três limites vêm do domínio: eram repetidos aqui e divergiriam na
# primeira vez que uma regra mudasse. Os nomes locais ficam como apelido para
# o texto do prompt, que fala de "student".
MIN_STUDENT_WORDS = MIN_WORDS
MAX_STUDENT_WORDS = MAX_WORDS

_URL = re.compile(r"(https?://|www\.)", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_MARKDOWN = re.compile(r"[*_`~]+")


@dataclass(frozen=True, slots=True)
class LessonBrief:
    """Recorte da aula que o parceiro pode usar. Nada aqui é do aluno."""

    course_slug: str
    lesson_number: int
    title: str
    goals: tuple[str, ...]
    focus_points: tuple[str, ...]
    target_terms: tuple[str, ...]
    phrases: tuple[str, ...]
    grammar_examples: tuple[str, ...]
    script: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Hint:
    code: CheckCode
    message: str


@dataclass(frozen=True, slots=True)
class PartnerTurn:
    partner_text: str
    hints: tuple[Hint, ...]
    confidence: float


def _plain(text: str) -> str:
    return " ".join(_MARKDOWN.sub("", text).split())


def brief_from_seed(lesson: Mapping[str, Any]) -> LessonBrief:
    """Constrói o recorte a partir do formato de `seed/lessons.json`.

    BE-46 fará o equivalente a partir das entidades do banco; os campos são os
    mesmos. Textos saem sem a marcação Markdown do seed.
    """

    grammar_examples: list[str] = []
    for block in lesson.get("grammar_blocks", ()):
        for row in block.get("rows", ()):
            cells = row.get("cells") or ()
            if cells:
                grammar_examples.append(_plain(str(cells[-1])))
    script: list[tuple[str, str]] = []
    for media in lesson.get("media", ()):
        for cue in media.get("cues", ()):
            speaker = str(cue.get("speaker") or "").strip()
            text = _plain(str(cue.get("text_en") or ""))
            if speaker and text:
                script.append((speaker, text))
        if script:
            break
    return LessonBrief(
        course_slug=str(lesson["course_slug"]),
        lesson_number=int(lesson["number"]),
        title=_plain(str(lesson["title"])),
        goals=tuple(_plain(str(g)) for g in lesson.get("goals", ())),
        focus_points=tuple(_plain(str(f)) for f in lesson.get("focus_points", ()) or ()),
        target_terms=tuple(
            _plain(str(v["term"])) for v in lesson.get("vocab", ()) if v.get("term")
        ),
        phrases=tuple(
            _plain(str(p["text_en"])) for p in lesson.get("phrases", ()) if p.get("text_en")
        ),
        grammar_examples=tuple(grammar_examples),
        script=tuple(script),
    )


def script_turns(
    brief: LessonBrief, partner_speaker: str | None = None
) -> tuple[dict[str, str], ...]:
    """Roteiro do modo `script`: quem fala cada linha. Sem IA.

    O parceiro assume `partner_speaker` (ou o primeiro falante). Com um único
    falante, todas as linhas viram `repeat` ("repita depois de mim").
    """

    speakers = tuple(dict.fromkeys(speaker for speaker, _ in brief.script))
    if not speakers:
        return ()
    partner = partner_speaker if partner_speaker in speakers else speakers[0]
    single = len(speakers) == 1
    turns: list[dict[str, str]] = []
    for speaker, text in brief.script:
        role = "repeat" if single else ("partner" if speaker == partner else "student")
        turns.append({"speaker": speaker, "role": role, "text_en": text})
    return tuple(turns)


def system_prompt(brief: LessonBrief, mode: Mode) -> str:
    """Instrução do parceiro, derivada só da aula. Versionada por PROMPT_VERSION."""

    goals = "\n".join(f"- {g}" for g in brief.goals) or "- (sem objetivos declarados)"
    terms = ", ".join(brief.target_terms) or "(nenhum)"
    phrases = "\n".join(f"- {p}" for p in brief.phrases[:8]) or "- (nenhuma)"
    examples = "\n".join(f"- {e}" for e in brief.grammar_examples[:8]) or "- (nenhum)"
    scope = {
        "script": "Follow the lesson dialogue closely; do not invent new topics.",
        "guided": "Ask one short question at a time about the lesson topic. Stay on it.",
        "free_unit": (
            "Talk only about this lesson's topic and its unit. If the learner changes the "
            "subject, answer briefly and bring the conversation back with a question."
        ),
    }[mode]
    return (
        f"[{PROMPT_VERSION}] You are a friendly conversation partner for an adult beginner "
        f'(CEFR A1) studying the lesson "{brief.title}" '
        f"(lesson {brief.lesson_number} of {brief.course_slug}).\n"
        "You are NOT a teacher and you NEVER grade, score, rate, or judge the learner. "
        "You NEVER comment on pronunciation. You NEVER ask for or mention personal data.\n"
        f"{scope}\n"
        "Speak only English in `partner_text`: one or two short sentences, simple present or "
        "the lesson's grammar, and end with a question when natural. Reuse the lesson "
        "vocabulary. Never include links, e-mail addresses, markdown or lists.\n"
        f"Lesson goals:\n{goals}\n"
        f"Target vocabulary: {terms}\n"
        f"Model phrases:\n{phrases}\n"
        f"Grammar examples:\n{examples}\n"
        "Hints: write each `hints[].message` in Brazilian Portuguese, one sentence, only "
        "for the codes listed in `failed_checks` of the user message, explaining what was "
        "missing without rewriting the learner's whole sentence. If `failed_checks` is "
        "empty, return an empty `hints` list.\n"
        "Answer ONLY with JSON that matches the provided schema."
    )


def response_schema(failed_codes: Sequence[CheckCode]) -> dict[str, Any]:
    """JSON Schema da resposta: `hints[].code` restrito aos códigos reprovados."""

    allowed = [code for code in CHECK_CODES if code in failed_codes]
    hint_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["code", "message"],
        "properties": {
            "code": {"type": "string", "enum": allowed or ["__none__"]},
            "message": {"type": "string", "minLength": 1, "maxLength": MAX_HINT_CHARS},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["partner_text", "hints", "confidence"],
        "properties": {
            "partner_text": {"type": "string", "minLength": 1, "maxLength": MAX_PARTNER_CHARS},
            "hints": {
                "type": "array",
                "items": hint_schema,
                "maxItems": min(MAX_HINTS, len(allowed)) if allowed else 0,
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def turn_messages(
    brief: LessonBrief,
    mode: Mode,
    transcript: str,
    failed_codes: Sequence[CheckCode],
    history: Sequence[tuple[Literal["student", "partner"], str]] = (),
    requested_terms: Sequence[str] = (),
) -> list[dict[str, str]]:
    """Mensagens no formato chat. Só texto da aula e do diálogo; nenhum dado do aluno."""

    recent = list(history)[-MAX_HISTORY_TURNS:]
    lines = [
        f"{'Learner' if role == 'student' else 'Partner'}: {_plain(text)}" for role, text in recent
    ]
    user = (
        "Conversation so far:\n" + ("\n".join(lines) if lines else "(start)") + "\n\n"
        f"Learner's latest turn (transcribed): {_plain(transcript) or '(nothing recognised)'}\n"
        f"Target terms for this turn: {', '.join(requested_terms) or '(none)'}\n"
        f"failed_checks: {list(failed_codes)}\n"
        "Reply with the partner's next turn and, only for failed_checks, one hint per code."
    )
    return [
        {"role": "system", "content": system_prompt(brief, mode)},
        {"role": "user", "content": user},
    ]


def sanitize_provider_output(raw: object, failed_codes: Sequence[CheckCode]) -> PartnerTurn | None:
    """Recusa ou limpa a resposta do provedor. `None` significa `invalid_provider_response`.

    Códigos fora de `failed_codes` são descartados (não invalidam); URL, e-mail,
    texto vazio ou longo demais invalidam. Confiança inválida vira 0.5, o valor
    conservador já usado na escrita assistida.
    """

    if not isinstance(raw, Mapping):
        return None
    text = raw.get("partner_text")
    if not isinstance(text, str):
        return None
    text = " ".join(text.split())
    if not text or len(text) > MAX_PARTNER_CHARS or _URL.search(text) or _EMAIL.search(text):
        return None
    hints_raw = raw.get("hints", [])
    if not isinstance(hints_raw, list):
        return None
    allowed = {code for code in CHECK_CODES if code in failed_codes}
    hints: list[Hint] = []
    for item in hints_raw:
        if not isinstance(item, Mapping):
            return None
        code, message = item.get("code"), item.get("message")
        if code not in allowed or not isinstance(message, str):
            continue
        message = " ".join(message.split())
        if (
            not message
            or len(message) > MAX_HINT_CHARS
            or _URL.search(message)
            or _EMAIL.search(message)
        ):
            return None
        if all(existing.code != code for existing in hints):
            hints.append(Hint(code=code, message=message))
        if len(hints) >= MAX_HINTS:
            break
    confidence_raw = raw.get("confidence", 0.5)
    confidence = (
        float(confidence_raw)
        if isinstance(confidence_raw, int | float) and 0 <= float(confidence_raw) <= 1
        else 0.5
    )
    return PartnerTurn(partner_text=text, hints=tuple(hints), confidence=round(confidence, 3))
