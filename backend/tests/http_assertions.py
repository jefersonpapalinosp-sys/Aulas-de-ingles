"""Falha na preparação deve ser identificada antes das asserções do cenário."""

from httpx import Response


def assert_status(response: Response, expected: int | None = None) -> Response:
    valid = response.is_success if expected is None else response.status_code == expected
    # Não incluir cookies, headers, query ou corpo potencialmente sensível no erro.
    assert valid, (
        f"{response.request.method} {response.request.url.path}: "
        f"HTTP {response.status_code}; esperado {expected or '2xx'}"
    )
    return response
