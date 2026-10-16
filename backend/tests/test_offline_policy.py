"""Apenas conteúdo editorial anônimo recebe opt-in para cache público."""

import pytest
from httpx import AsyncClient

from app.services.offline_policy import if_none_match_matches, public_text_path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/courses",
        "/api/courses/voa-level-1/curriculum",
        "/api/courses/voa-level-1/lessons/31",
        "/api/courses/voa-level-1/lessons/31/exercises",
        "/api/lessons",
        "/api/lessons/31",
        "/api/exercises",
        "/api/vocab",
    ],
)
async def test_public_editorial_opt_in(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 200
    assert response.headers["x-aulas-offline"] == "public-text-v1"
    assert response.headers["cache-control"] == "public, max-age=0, must-revalidate"
    assert response.headers["etag"].startswith('"')
    assert response.headers["etag"].endswith('"')
    # Um cabeçalho de autenticação não personaliza esses endpoints públicos.
    other = await client.get(path, headers={"Authorization": "Bearer not-a-session"})
    assert other.status_code == 200
    assert other.json() == response.json()
    assert other.headers["etag"] == response.headers["etag"]


@pytest.mark.asyncio
async def test_public_editorial_supports_conditional_get(client: AsyncClient) -> None:
    initial = await client.get("/api/courses")
    etag = initial.headers["etag"]

    cached = await client.get("/api/courses", headers={"If-None-Match": etag})
    weak_cached = await client.get("/api/courses", headers={"If-None-Match": f'"other", W/{etag}'})

    for response in (cached, weak_cached):
        assert response.status_code == 304
        assert response.content == b""
        assert response.headers["etag"] == etag
        assert response.headers["cache-control"] == ("public, max-age=0, must-revalidate")
        assert response.headers["x-aulas-offline"] == "public-text-v1"
        assert "content-type" not in response.headers


@pytest.mark.asyncio
async def test_private_response_never_exposes_etag(client: AsyncClient) -> None:
    response = await client.get("/api/me", headers={"If-None-Match": "*"})

    assert response.status_code >= 400
    assert response.headers["cache-control"] == "private, no-store"
    assert "etag" not in response.headers


@pytest.mark.parametrize(
    ("header", "matches"),
    [(None, False), ('"different"', False), ("*", True), ('W/"value"', True)],
)
def test_if_none_match_comparison(header: str | None, matches: bool) -> None:
    assert if_none_match_matches(header, '"value"') is matches


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/me"),
        ("GET", "/api/courses/voa-level-1/lessons/9999"),
        ("GET", "/api/courses/voa-level-1/lessons/31/study-session"),
        ("GET", "/api/lessons/invalid"),
        ("POST", "/api/courses"),
    ],
)
async def test_private_errors_and_mutations_never_opt_in(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path)
    assert response.status_code >= 400
    assert "x-aulas-offline" not in response.headers
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(
    "path",
    [
        "/api/me",
        "/api/media/1",
        "/api/auth/refresh",
        "/api/speaking/1/audio",
        "/api/courses/voa-level-1/completion",
        "/api/courses/voa-level-1/lessons/31/writing",
    ],
)
def test_path_allowlist_rejects_private_data(path: str) -> None:
    assert not public_text_path(path)
