"""Tabela-verdade do SM-2."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.sm2 import EASE_INICIAL, EASE_MINIMO, Estado, revisar

AGORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def test_primeira_revisao_certa_volta_em_um_dia() -> None:
    novo, quando = revisar(Estado(), 4, AGORA)
    assert novo.interval_days == 1
    assert novo.repetitions == 1
    assert quando == AGORA + timedelta(days=1)


def test_segunda_revisao_certa_volta_em_seis_dias() -> None:
    estado, _ = revisar(Estado(), 4, AGORA)
    estado, quando = revisar(estado, 4, AGORA)
    assert estado.interval_days == 6
    assert quando == AGORA + timedelta(days=6)


def test_da_terceira_em_diante_o_intervalo_multiplica_pelo_ease() -> None:
    estado = Estado(ease_factor=2.5, interval_days=6, repetitions=2)
    novo, _ = revisar(estado, 4, AGORA)
    # 6 × 2.5 = 15, usando o ease anterior à revisão (ordem do SM-2 original)
    assert novo.interval_days == 15
    assert novo.repetitions == 3


@pytest.mark.parametrize(
    ("nota", "esperado"),
    [(5, EASE_INICIAL + 0.1), (4, EASE_INICIAL), (3, EASE_INICIAL - 0.14)],
)
def test_ease_sobe_desce_ou_fica(nota: int, esperado: float) -> None:
    novo, _ = revisar(Estado(), nota, AGORA)
    assert novo.ease_factor == pytest.approx(esperado)


def test_errar_zera_a_sequencia_e_conta_lapso() -> None:
    estado = Estado(ease_factor=2.5, interval_days=15, repetitions=3)
    novo, quando = revisar(estado, 1, AGORA)
    assert novo.repetitions == 0
    assert novo.interval_days == 1
    assert novo.lapses == 1
    assert quando == AGORA + timedelta(days=1)
    # Mas a dificuldade acumulada não é jogada fora.
    assert novo.ease_factor < 2.5


def test_ease_nunca_desce_do_piso() -> None:
    estado = Estado()
    for _ in range(10):
        estado, _ = revisar(estado, 0, AGORA)
    assert estado.ease_factor == EASE_MINIMO
    assert estado.lapses == 10


def test_nota_fora_da_faixa_e_erro() -> None:
    for nota in (-1, 6):
        with pytest.raises(ValueError, match="entre 0 e 5"):
            revisar(Estado(), nota, AGORA)


def test_trinta_dias_de_acerto_perfeito() -> None:
    """A curva precisa abrir: 1, 6, 16, 41… e não ficar presa em um dia."""
    estado = Estado()
    quando = AGORA
    curva = []
    for _ in range(6):
        estado, quando = revisar(estado, 5, quando)
        curva.append(estado.interval_days)
    assert curva == [1, 6, 16, 45, 130, 390]
    assert quando > AGORA + timedelta(days=30)


def test_trinta_dias_com_um_lapso_no_quinto_dia() -> None:
    """Depois do tropeço a carta recomeça, mas mais devagar que da primeira vez."""
    estado = Estado()
    quando = AGORA
    estado, quando = revisar(estado, 4, quando)  # dia 0  -> volta no dia 1
    estado, quando = revisar(estado, 4, quando)  # dia 1  -> volta no dia 7
    assert estado.interval_days == 6

    estado, quando = revisar(estado, 1, quando)  # errou
    assert estado.interval_days == 1
    assert estado.lapses == 1
    ease_depois_do_lapso = estado.ease_factor

    estado, quando = revisar(estado, 4, quando)
    estado, quando = revisar(estado, 4, quando)
    estado, quando = revisar(estado, 4, quando)
    # Mesma posição na sequência, mas com ease menor: o intervalo é menor que
    # os 15 dias que uma carta sem lapso teria aqui.
    assert estado.ease_factor == pytest.approx(ease_depois_do_lapso)
    assert estado.interval_days < 15
    assert estado.interval_days == round(6 * ease_depois_do_lapso)


def test_intervalo_nunca_e_zero() -> None:
    """round(1 × 1.3) = 1; mas um ease baixo com intervalo 1 não pode zerar."""
    estado = Estado(ease_factor=EASE_MINIMO, interval_days=1, repetitions=5)
    novo, _ = revisar(estado, 3, AGORA)
    assert novo.interval_days >= 1
