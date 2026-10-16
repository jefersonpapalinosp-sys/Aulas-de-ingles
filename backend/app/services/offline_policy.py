"""Opt-in restrito ao conteúdo editorial público, nunca ao progresso pessoal."""

import re
from hashlib import sha256

_PUBLIC_TEXT = re.compile(
    r"/api/(?:courses|lessons|exercises|vocab|lessons/[0-9]+|"
    r"courses/[a-z0-9-]+/(?:curriculum|lessons/[0-9]+(?:/exercises)?))"
)


def public_text_path(path: str) -> bool:
    return _PUBLIC_TEXT.fullmatch(path) is not None


def public_content_etag(body: bytes) -> str:
    """Gera um validador forte, estável e independente da instância da API."""

    return f'"{sha256(body).hexdigest()}"'


def if_none_match_matches(header: str | None, etag: str) -> bool:
    """Aplica a comparação fraca exigida por If-None-Match em requisições GET."""

    if header is None:
        return False
    expected = etag.removeprefix("W/")
    return any(
        candidate == "*" or candidate.removeprefix("W/") == expected
        for candidate in (part.strip() for part in header.split(","))
    )
