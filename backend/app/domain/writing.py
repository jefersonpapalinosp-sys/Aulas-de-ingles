"""Feedback determinístico para produção escrita curta."""

import re
from dataclasses import dataclass

WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$")


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
    lowered_words = {word.lower().replace("’", "'") for word in words}
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
        label = str(requirement.get("label", "Requisito da aula"))
        raw_terms = requirement.get("terms", [])
        terms = [str(term).lower() for term in raw_terms] if isinstance(raw_terms, list) else []
        checks.append(
            WritingCheck(
                code=f"requirement_{index}",
                label=label,
                passed=any(term in lowered_words for term in terms),
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
