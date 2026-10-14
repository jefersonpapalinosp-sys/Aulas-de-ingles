"""Feedback determinístico para produção escrita curta."""

import hashlib
import json
import re
from dataclasses import dataclass

from app.domain.writing_rubric import WritingRequirement, normalize_marker

WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$")


def requirement_passes(text: str, requirement: WritingRequirement) -> bool:
    """Conta evidências literais sem sobrepor alternativas (want / want to).

    A pontuação de uma expressão é literal: não se atravessa ponto/vírgula
    ausente no marcador. Espaços, caixa e apóstrofos tipográficos normalizam.
    Marcadores iniciados por apóstrofo representam sufixos de contrações,
    como 'll be em I'll be. Não se expande 'd ambiguamente para had/would.
    """
    normalized = normalize_marker(text)
    if requirement.kind == "quoted_speech":
        quotes = re.findall(r'"([^"\n]+)"|“([^”\n]+)”', normalized)
        return (
            sum(bool(WORD_RE.search(left or right)) for left, right in quotes)
            >= requirement.min_count
        )

    candidates: list[tuple[int, int, int]] = []
    for index, term in enumerate(requirement.terms):
        boundary = r"(?<=[a-z])" if term.startswith("'") else r"(?<![\w'-])"
        pattern = boundary + re.escape(term).replace(r"\ ", r"\s+") + r"(?![\w'-])"
        candidates.extend(
            (match.start(), match.end(), index) for match in re.finditer(pattern, normalized)
        )
    counts = [0] * len(requirement.terms)
    end = -1
    for start, stop, index in sorted(candidates, key=lambda item: (item[0], -item[1], item[2])):
        if start >= end:
            counts[index] += 1
            end = stop
    if requirement.match_mode == "all":
        return all(count >= requirement.min_count for count in counts)
    observed = (
        sum(count > 0 for count in counts)
        if requirement.count_mode == "distinct_terms"
        else sum(counts)
    )
    return observed >= requirement.min_count


def rubric_snapshot(
    *,
    title: str,
    instructions: str,
    min_words: int,
    min_sentences: int,
    requirements: list[dict[str, object]],
) -> tuple[str, dict[str, object]]:
    snapshot: dict[str, object] = {
        "schema_version": 2,
        "title": title,
        "instructions": instructions,
        "min_words": min_words,
        "min_sentences": min_sentences,
        "requirements": [
            WritingRequirement.model_validate(item).model_dump() for item in requirements
        ],
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(), snapshot


@dataclass(frozen=True)
class WritingCheck:
    code: str
    label: str
    passed: bool
    suggestion: str


def analyze_writing(
    text: str,
    *,
    min_words: int,
    min_sentences: int,
    requirements: list[dict[str, object]],
) -> tuple[int, int, list[WritingCheck]]:
    words = WORD_RE.findall(text)
    sentences = [part.strip() for part in SENTENCE_RE.findall(text) if part.strip()]
    checks = [
        WritingCheck(
            code="word_count",
            label=f"Pelo menos {min_words} palavras",
            passed=len(words) >= min_words,
            suggestion=f"Acrescente detalhes até chegar a {min_words} palavras.",
        ),
        WritingCheck(
            code="sentence_count",
            label=f"Pelo menos {min_sentences} frases",
            passed=len(sentences) >= min_sentences,
            suggestion=f"Desenvolva sua ideia em pelo menos {min_sentences} frases.",
        ),
    ]
    for index, requirement in enumerate(requirements):
        rule = WritingRequirement.model_validate(requirement)
        label = rule.label
        checks.append(
            WritingCheck(
                code=f"requirement_{index}",
                label=label,
                passed=requirement_passes(text, rule),
                suggestion=f"Inclua {label.lower()}.",
            )
        )
    stripped = text.strip()
    checks.extend(
        [
            WritingCheck(
                code="capitalization",
                label="Começar com letra maiúscula",
                passed=bool(stripped and stripped[0].isupper()),
                suggestion="Comece a primeira frase com letra maiúscula.",
            ),
            WritingCheck(
                code="ending_punctuation",
                label="Terminar com pontuação",
                passed=bool(stripped and stripped[-1] in ".!?"),
                suggestion="Finalize o texto com ponto, interrogação ou exclamação.",
            ),
        ]
    )
    return len(words), len(sentences), checks
