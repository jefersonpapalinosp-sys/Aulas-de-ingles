"""Contrato de critérios observáveis; não é uma análise sintática de inglês."""

import re
import unicodedata
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALGORITHM_VERSION = "writing-rules-v2"
EVALUATION_SCOPE = (
    "Verificação de tamanho, pontuação e marcadores da rubrica. "
    "Não garante gramática correta, coerência ou atendimento completo à proposta."
)


def normalize_marker(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    replacements: dict[str, str | int | None] = {"’": "'", "‘": "'", "‑": "-", "‐": "-"}
    return " ".join(value.translate(str.maketrans(replacements)).split())


class WritingRequirement(BaseModel):
    """Termos são palavras ou expressões literais, nunca regex editorial.

    any: mínimo de ocorrências não sobrepostas ou de termos distintos.
    all: cada termo precisa ocorrer min_count vezes. Aspas exigem par fechado.
    Os defaults permitem ler rubricas antigas até a reaplicação do seed.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=300)
    terms: list[str] = Field(max_length=40)
    kind: Literal["markers", "quoted_speech"] = "markers"
    match_mode: Literal["any", "all"] = "any"
    count_mode: Literal["occurrences", "distinct_terms"] = "occurrences"
    min_count: int = Field(default=1, ge=1, le=20, strict=True)

    @model_validator(mode="before")
    @classmethod
    def legacy_quotes(cls, value: Any) -> Any:
        # Uma rubrica antiga buscava aspas no tokenizer que só retorna palavras.
        if isinstance(value, dict) and "kind" not in value and value.get("terms") == ['"', "“"]:
            return {**value, "kind": "quoted_speech", "terms": []}
        return value

    @field_validator("label")
    @classmethod
    def label_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Rótulo vazio.")
        return value.strip()

    @field_validator("terms")
    @classmethod
    def normalize_terms(cls, values: list[str]) -> list[str]:
        normalized = [normalize_marker(value) for value in values]
        if any(
            not value or len(value) > 150 or not re.search("[a-z]", value) for value in normalized
        ):
            raise ValueError("Cada marcador precisa conter palavras em inglês, sem termos vazios.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Marcadores repetidos após normalização.")
        return normalized

    @model_validator(mode="after")
    def consistent_rule(self) -> Self:
        if self.kind == "quoted_speech":
            if self.terms or self.match_mode != "any" or self.count_mode != "occurrences":
                raise ValueError("Fala entre aspas usa pares de aspas, não termos ou alternativas.")
        elif not self.terms:
            raise ValueError("Critério de marcadores exige ao menos um termo.")
        if self.count_mode == "distinct_terms" and (
            self.match_mode != "any" or self.min_count > len(self.terms)
        ):
            raise ValueError("Quantidade de termos distintos incompatível com a regra.")
        return self
