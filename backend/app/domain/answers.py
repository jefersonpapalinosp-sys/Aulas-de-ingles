"""Comparação de respostas — lógica pura, sem banco e sem HTTP.

Fica isolada para que correção, feedback e revisão usem exatamente a mesma
normalização. Regra que muda de lugar vira regra que diverge.
"""

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


def acertou(resposta: str, aceitas: list[str]) -> bool:
    """True quando a resposta bate com qualquer uma das aceitas."""
    if not resposta.strip():
        return False
    alvo = normalizar(resposta)
    return any(normalizar(a) == alvo for a in aceitas)


def analisar_resposta(resposta: str, aceitas: list[str]) -> AnswerFeedback:
    """Classifica o erro sem devolver palavras da resposta esperada."""
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
