"""Regras de comparação de resposta."""

import pytest

from app.domain.answers import acertou, normalizar


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Faster", "faster"),
        ("  faster  ", "faster"),
        ("faster.", "faster"),
        ("Won't", "won't"),
        ("won’t", "won't"),  # apóstrofo tipográfico
        ("the  most   serious", "the most serious"),
        ("I disagree!", "i disagree"),
    ],
)
def test_normalizacao(entrada: str, esperado: str) -> None:
    assert normalizar(entrada) == esperado


def test_aceita_qualquer_uma_das_respostas_certas() -> None:
    aceitas = ["should", "ought to"]
    assert acertou("should", aceitas)
    assert acertou("Ought To", aceitas)
    assert not acertou("must", aceitas)


def test_resposta_vazia_nunca_acerta() -> None:
    assert not acertou("", ["faster"])
    assert not acertou("   ", ["faster"])


def test_acento_nao_e_ignorado() -> None:
    """Em inglês não aparece, mas apagar acento quebraria resposta em português."""
    assert normalizar("sílaba") == "sílaba"
    assert not acertou("silaba", ["sílaba"])
