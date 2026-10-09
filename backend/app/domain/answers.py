"""Comparação de respostas — lógica pura, sem banco e sem HTTP.

Fica isolada para que correção, feedback e revisão usem exatamente a mesma
normalização. Regra que muda de lugar vira regra que diverge.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

_PONTUACAO = re.compile(r"[.,!?;:\"“”]")
_ESPACOS = re.compile(r"\s+")

FeedbackCategory = Literal[
    "correct", "missing_word", "extra_word", "word_order", "spelling", "word_choice"
]


@dataclass(frozen=True)
class FeedbackToken:
    text: str
    status: Literal["keep", "review"]


@dataclass(frozen=True)
class AnswerFeedback:
    category: FeedbackCategory
    message: str
    tokens: list[FeedbackToken]


def normalizar(resposta: str) -> str:
    """Põe a resposta na forma em que duas respostas podem ser comparadas.

    Ignora caixa, pontuação, espaço sobrando e o tipo de apóstrofo — digitar
    `Won't`, `wont` ou `won’t` não pode ser a diferença entre acerto e erro.
    O que ela **não** ignora é acento: em inglês isso não aparece, e apagar
    acento quebraria qualquer resposta em português no futuro.
    """
    texto = unicodedata.normalize("NFC", resposta).strip().casefold()
    texto = texto.replace("’", "'").replace("`", "'")
    texto = _PONTUACAO.sub("", texto)
    return _ESPACOS.sub(" ", texto).strip()


def _classification_pairs(pairs: list[tuple[str, object]]) -> dict[str, str]:
    """Constrói um mapa e rejeita chaves duplicadas em vez de sobrescrevê-las."""
    result: dict[str, str] = {}
    for key, value in pairs:
        if key in result or not isinstance(value, str):
            raise ValueError
        result[key] = value
    return result


def parse_classification(answer: str) -> dict[str, str] | None:
    """Lê a resposta estruturada sem aceitar arrays, valores vazios ou duplicatas."""
    try:
        value = json.loads(answer, object_pairs_hook=_classification_pairs)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(value, dict) or not value:
        return None
    if not all(
        isinstance(item, str) and item.strip() and isinstance(category, str) and category.strip()
        for item, category in value.items()
    ):
        return None
    return value


def _normalized_classification(value: dict[str, str]) -> dict[str, str] | None:
    normalized: dict[str, str] = {}
    for item, category in value.items():
        key = _ESPACOS.sub(" ", unicodedata.normalize("NFC", item).strip()).casefold()
        normalized_category = _ESPACOS.sub(
            " ", unicodedata.normalize("NFC", category).strip()
        ).casefold()
        if key in normalized:
            return None
        normalized[key] = normalized_category
    return normalized


def canonicalizar_classificacao(answer: str) -> str | None:
    """Normaliza e ordena um mapa item→categoria para comparação semântica."""
    value = parse_classification(answer)
    if value is None:
        return None
    normalized = _normalized_classification(value)
    if normalized is None:
        return None
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validar_e_canonicalizar_classificacao(
    answer: str, items: list[str], categories: list[str]
) -> str:
    """Valida o contrato público e devolve JSON estável para persistência.

    Os nomes precisam coincidir com os publicados no exercício. Isso impede
    respostas parciais, categorias inventadas e chaves extras.
    """
    value = parse_classification(answer)
    if value is None or set(value) != set(items):
        raise ValueError("A classificação deve atribuir uma categoria a cada item.")
    allowed_categories = set(categories)
    if any(category not in allowed_categories for category in value.values()):
        raise ValueError("A classificação contém uma categoria desconhecida.")
    ordered = {item: value[item] for item in sorted(items)}
    return json.dumps(ordered, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def acertou(resposta: str, aceitas: list[str]) -> bool:
    """True quando a resposta bate com qualquer uma das aceitas."""
    if not resposta.strip():
        return False
    structured = canonicalizar_classificacao(resposta)
    if structured is not None:
        return any(canonicalizar_classificacao(answer) == structured for answer in aceitas)
    alvo = normalizar(resposta)
    return any(normalizar(a) == alvo for a in aceitas)


def analisar_resposta(resposta: str, aceitas: list[str]) -> AnswerFeedback:
    """Classifica o erro sem devolver palavras da resposta esperada."""
    structured = parse_classification(resposta)
    if structured is not None and any(
        parse_classification(answer) is not None for answer in aceitas
    ):
        correct = acertou(resposta, aceitas)
        submitted = _normalized_classification(structured) or {}
        classification_targets: list[dict[str, str]] = []
        for accepted in aceitas:
            parsed_target = parse_classification(accepted)
            if parsed_target is None:
                continue
            normalized_target = _normalized_classification(parsed_target)
            if normalized_target is not None:
                classification_targets.append(normalized_target)
        closest_classification = max(
            classification_targets,
            key=lambda candidate: sum(
                candidate.get(item) == category for item, category in submitted.items()
            ),
            default={},
        )
        return AnswerFeedback(
            category="correct" if correct else "word_choice",
            message=(
                "A classificação corresponde à organização esperada."
                if correct
                else "Revise as categorias dos itens marcados e tente novamente."
            ),
            tokens=[
                FeedbackToken(
                    text=f"{item}: {category}",
                    status=(
                        "keep"
                        if correct
                        or closest_classification.get(
                            _ESPACOS.sub(" ", unicodedata.normalize("NFC", item).strip()).casefold()
                        )
                        == _ESPACOS.sub(
                            " ", unicodedata.normalize("NFC", category).strip()
                        ).casefold()
                        else "review"
                    ),
                )
                for item, category in structured.items()
            ],
        )
    normalized = normalizar(resposta)
    input_tokens = normalized.split()
    if acertou(resposta, aceitas):
        return AnswerFeedback(
            category="correct",
            message="A resposta corresponde a uma das formas aceitas.",
            tokens=[FeedbackToken(text=token, status="keep") for token in input_tokens],
        )

    targets = [normalizar(answer).split() for answer in aceitas]
    target = max(
        targets,
        key=lambda candidate: SequenceMatcher(None, input_tokens, candidate).ratio(),
        default=[],
    )
    matcher = SequenceMatcher(None, input_tokens, target)
    kept_indexes = {
        index
        for tag, start, end, _, _ in matcher.get_opcodes()
        if tag == "equal"
        for index in range(start, end)
    }
    tokens = [
        FeedbackToken(text=token, status="keep" if index in kept_indexes else "review")
        for index, token in enumerate(input_tokens)
    ]

    if len(input_tokens) < len(target):
        category: FeedbackCategory = "missing_word"
        message = "Parece faltar uma palavra ou parte da estrutura. Use uma dica e tente novamente."
    elif len(input_tokens) > len(target):
        category = "extra_word"
        message = "Há uma palavra ou estrutura a mais. Revise os trechos marcados."
    elif sorted(input_tokens) == sorted(target):
        category = "word_order"
        message = "As palavras parecem adequadas, mas a ordem precisa ser revista."
    elif SequenceMatcher(None, normalized, " ".join(target)).ratio() >= 0.75:
        category = "spelling"
        message = "A resposta está próxima. Confira a ortografia dos trechos marcados."
    else:
        category = "word_choice"
        message = "Revise a escolha das palavras marcadas e tente novamente."

    return AnswerFeedback(category=category, message=message, tokens=tokens)
