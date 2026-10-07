"""Gate de contrato.

O openapi.json versionado é o baseline. Se o código muda a API, este teste
quebra e o diff do contrato aparece no PR — que é o ponto: mudança de
contrato é decisão consciente, não efeito colateral.
"""

from app.openapi_dump import BASELINE, dumps


def test_contrato_bate_com_o_baseline_versionado() -> None:
    atual = dumps()
    commitado = BASELINE.read_text(encoding="utf-8")
    assert atual == commitado, (
        "O contrato OpenAPI mudou. Rode `make openapi`, confira o diff e "
        "commite o backend/openapi.json junto com a mudança."
    )
