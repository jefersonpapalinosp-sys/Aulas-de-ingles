"""SM-2 — o algoritmo de repetição espaçada do SuperMemo 2.

Função pura: recebe o estado de uma carta e a nota que a pessoa deu, devolve
o próximo estado. Sem banco, sem relógio global, sem HTTP — o `agora` entra
como argumento para o teste poder simular trinta dias sem esperar trinta dias.

A nota vai de 0 a 5, como no algoritmo original:

    0-2  errou         zera a sequência e conta um lapso
    3    acertou duro  mantém a sequência, mas derruba o fator de facilidade
    4    acertou       o caso normal
    5    fácil demais  sobe o fator de facilidade
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

# Piso do fator de facilidade. Sem ele, uma carta difícil encolhe o intervalo
# até voltar todo dia para sempre.
EASE_MINIMO = 1.3
EASE_INICIAL = 2.5
# Abaixo disto a resposta conta como erro.
NOTA_MINIMA_DE_ACERTO = 3


@dataclass(frozen=True)
class Estado:
    """Estado de uma carta. Imutável: cada revisão produz um estado novo."""

    ease_factor: float = EASE_INICIAL
    interval_days: int = 0
    repetitions: int = 0
    lapses: int = 0


def _novo_ease(ease: float, nota: int) -> float:
    """Fórmula do SM-2, aplicada em toda revisão — inclusive nas erradas.

    O resultado é arredondado a duas casas de propósito. Somar 0.1 repetidas
    vezes em float acumula erro (2.8 + 0.1 = 2.9000000000000004), e esse erro
    chega ao intervalo: 45 × 2.9000000000000004 dá 130.50000000000003, que
    arredonda para 131 em vez de 130. Duas casas é a precisão que o algoritmo
    realmente usa, e deixa a curva reproduzível.
    """
    ajuste = 0.1 - (5 - nota) * (0.08 + (5 - nota) * 0.02)
    return round(max(EASE_MINIMO, ease + ajuste), 2)


def revisar(estado: Estado, nota: int, agora: datetime) -> tuple[Estado, datetime]:
    """Aplica uma revisão e devolve (novo estado, quando revisar de novo).

    Erro não zera o fator de facilidade, só a sequência: a dificuldade que a
    carta já demonstrou é informação acumulada, e jogá-la fora faria a carta
    recomeçar fácil demais toda vez.
    """
    if not 0 <= nota <= 5:
        raise ValueError(f"nota precisa estar entre 0 e 5, recebi {nota}")

    # Ordem do SM-2 original: o intervalo é calculado com o fator de
    # facilidade **anterior**, e só depois o fator é atualizado. Inverter os
    # dois adianta o efeito de uma revisão em um passo e faz a curva divergir.
    if nota < NOTA_MINIMA_DE_ACERTO:
        intervalo, repeticoes, lapsos = 1, 0, estado.lapses + 1
    else:
        if estado.repetitions == 0:
            intervalo = 1
        elif estado.repetitions == 1:
            intervalo = 6
        else:
            # round() do Python arredonda .5 para o par mais próximo
            # (130.5 -> 130). É o mesmo critério todas as vezes, e com o ease
            # em duas casas o resultado é determinístico.
            intervalo = max(1, round(estado.interval_days * estado.ease_factor))
        repeticoes, lapsos = estado.repetitions + 1, estado.lapses

    novo = Estado(
        ease_factor=_novo_ease(estado.ease_factor, nota),
        interval_days=intervalo,
        repetitions=repeticoes,
        lapses=lapsos,
    )
    return novo, agora + timedelta(days=novo.interval_days)
