"""Checks determinísticos de um turno do aluno no parceiro de conversa.

Módulo puro: recebe texto e o recorte da aula, devolve códigos. Nada de banco,
provedor, relógio ou aleatoriedade — é o que permite testar cada regra sem
subir nada e, mais importante, é o que define o **limite do que o modelo pode
dizer**: o provedor só recebe os códigos reprovados aqui e só pode devolver
dicas para eles (ADR `adr_assistente_de_conversa.md`).

A separação importa por uma razão de produto, não de arquitetura: a avaliação
do aluno é determinística e auditável. O modelo explica; ele não julga. Se um
dia o provedor sair do ar, a avaliação continua idêntica — muda só a dica.

Os quatro códigos são estáveis e fazem parte do contrato HTTP; mudar um nome
quebra cliente e histórico.
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.domain.answers import normalizar

CheckCode = Literal[
    "target_terms_missing",
    "grammar_pattern_missing",
    "too_short",
    "too_long",
]
# A ordem é a da avaliação e também a do `enum` enviado ao provedor; quem
# precisa iterar os códigos usa esta tupla, não uma segunda lista.
CHECK_CODES: tuple[CheckCode, ...] = (
    "target_terms_missing",
    "grammar_pattern_missing",
    "too_short",
    "too_long",
)

MIN_WORDS = 3
MAX_WORDS = 60
# Limite de turnos do aluno por diálogo no Guiado, decidido em 26/10/2026: com
# o STT p95 de 3,6 s mais ~2 s do modelo, doze turnos dão uma conversa de 6 a
# 10 minutos contando a fala do aluno — um bloco de estudo inteiro. A cota
# diária é múltiplo deste número (ver `Settings.assist_dialogue_daily_turns`).
MAX_TURNS_PER_DIALOGUE = 12

# Apenas conteúdo editorial e cobertura; nunca uma cópia da fala do aluno.
CheckDetails = dict[str, list[dict[str, str | bool]]]

# Fronteira de palavra sobre o texto já normalizado. `\b` não serve: o termo
# pode conter apóstrofo ("don't") e, em alguns motores, `\b` quebra ali.
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*", re.UNICODE)


def _fold(text: str) -> list[str]:
    """Palavras comparáveis para **cobertura de termo**, sem apóstrofo.

    Aqui a tolerância é maior que em `answers.acertou`, e de propósito: são
    perguntas diferentes. A correção de exercício pergunta "esta é a resposta
    esperada?", e quem escolheu a grafia foi o aluno. A cobertura pergunta
    "este vocabulário apareceu na fala?", e quem escolheu a grafia foi o
    transcritor. Se o STT escrever "dont" onde o aluno disse "don't", contar
    como ausente seria um falso negativo — e pior que um número errado: o
    modelo receberia `target_terms_missing` e devolveria uma dica pedindo algo
    que o aluno acabou de fazer.
    """
    return [palavra.replace("'", "") for palavra in _WORD.findall(normalizar(text))]


@dataclass(frozen=True)
class TurnExpectation:
    """O que este turno pede do aluno, vindo do recorte da aula.

    `target_terms` são termos de `vocab_item` da aula; `grammar_patterns` são
    trechos extraídos dos exemplos de `grammar_block`. Ambos podem ser vazios:
    um turno de abertura não exige nada, e aí o aluno só precisa falar algo de
    tamanho razoável.
    """

    target_terms: tuple[str, ...] = ()
    grammar_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class TurnCheck:
    code: CheckCode
    passed: bool
    detail: str


def words(text: str) -> list[str]:
    """Palavras reconhecíveis do texto normalizado, para contagem e cobertura."""
    return _WORD.findall(normalizar(text))


def _contains_phrase(haystack: list[str], needle: str) -> bool:
    """Procura o termo como sequência de palavras, não como substring.

    Substring acusaria "can" dentro de "cancel" e daria por cumprido um termo
    que o aluno não falou. Termo de várias palavras ("ought to") precisa
    aparecer na ordem, em palavras adjacentes.
    """
    alvo = _fold(needle)
    if not alvo:
        return False
    limite = len(haystack) - len(alvo)
    return any(haystack[i : i + len(alvo)] == alvo for i in range(limite + 1))


def _covered(text: str, expected: tuple[str, ...]) -> tuple[str, ...]:
    dobrado = _fold(text)
    return tuple(termo for termo in expected if _contains_phrase(dobrado, termo))


def evaluation_details(text: str, expectation: TurnExpectation) -> CheckDetails:
    """Recorte histórico usando a mesma regra de cobertura dos checks."""
    details: CheckDetails = {}
    for name, expected in (
        ("target_terms", expectation.target_terms),
        ("grammar_patterns", expectation.grammar_patterns),
    ):
        covered = _covered(text, expected)
        details[name] = [{"text": term, "covered": term in covered} for term in expected]
    return details


def evaluate(text: str, expectation: TurnExpectation) -> tuple[TurnCheck, ...]:
    """Avalia o turno e devolve um check por regra aplicável, na ordem fixa.

    Regras sem expectativa declarada não entram no resultado: um turno sem
    termo-alvo não deve produzir `target_terms_missing` aprovado, porque isso
    sugeriria ao aluno que ele cumpriu algo que não foi pedido.

    `target_terms` é satisfeito por **um** termo, não por todos: o objetivo é
    puxar o vocabulário da aula para a fala, não transformar a conversa em
    lista de palavras obrigatórias.
    """
    spoken = words(text)
    total = len(spoken)
    checks: list[TurnCheck] = []

    if expectation.target_terms:
        cobertos = _covered(text, expectation.target_terms)
        checks.append(
            TurnCheck(
                code="target_terms_missing",
                passed=bool(cobertos),
                detail=(
                    f"usou {', '.join(cobertos)}"
                    if cobertos
                    else f"nenhum de {', '.join(expectation.target_terms)}"
                ),
            )
        )

    if expectation.grammar_patterns:
        padroes = _covered(text, expectation.grammar_patterns)
        checks.append(
            TurnCheck(
                code="grammar_pattern_missing",
                passed=bool(padroes),
                detail=(
                    f"usou {', '.join(padroes)}"
                    if padroes
                    else f"nenhum de {', '.join(expectation.grammar_patterns)}"
                ),
            )
        )

    # Tamanho é sempre avaliado: vale para qualquer turno, inclusive o de
    # abertura. Silêncio transcrito como string vazia reprova por `too_short`,
    # que é a leitura certa — não há nada a comentar sobre o que não foi dito.
    checks.append(
        TurnCheck(
            code="too_short",
            passed=total >= MIN_WORDS,
            detail=f"{total} palavra(s), mínimo {MIN_WORDS}",
        )
    )
    checks.append(
        TurnCheck(
            code="too_long",
            passed=total <= MAX_WORDS,
            detail=f"{total} palavra(s), máximo {MAX_WORDS}",
        )
    )
    return tuple(checks)


def failed_codes(checks: tuple[TurnCheck, ...]) -> tuple[CheckCode, ...]:
    """Só os reprovados, na ordem da avaliação.

    É exatamente esta lista que vai ao provedor e que restringe o `enum` do
    JSON Schema da resposta: o modelo não pode inventar um código, porque não
    recebe nenhum outro.
    """
    return tuple(check.code for check in checks if not check.passed)
