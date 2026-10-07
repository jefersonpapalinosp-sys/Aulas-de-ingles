"""Comparação de respostas — lógica pura, sem banco e sem HTTP.

Fica isolada porque a S3 vai reusar exatamente esta normalização para gravar
tentativas, e a S4 para decidir o que entra no deck de revisão. Regra que muda
de lugar vira regra que diverge.
"""

import re
import unicodedata

_PONTUACAO = re.compile(r"[.,!?;:\"“”]")
_ESPACOS = re.compile(r"\s+")


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
