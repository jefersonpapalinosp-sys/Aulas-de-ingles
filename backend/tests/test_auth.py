"""Registro, login, refresh, logout e o que acontece sem token."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import criar_token


def credenciais(sufixo: str) -> dict[str, str]:
    return {
        "email": f"Teste.{sufixo}@Exemplo.com",
        "password": "senha-bem-grande",
        "display_name": "Jeferson",
    }


async def registrar(client: AsyncClient, sufixo: str) -> str:
    r = await client.post("/api/auth/register", json=credenciais(sufixo))
    assert r.status_code == 201, r.text
    token: str = r.json()["access_token"]
    return token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_registro_devolve_access_e_grava_cookie(client: AsyncClient) -> None:
    r = await client.post("/api/auth/register", json=credenciais("novo"))
    assert r.status_code == 201
    assert r.json()["token_type"] == "bearer"
    assert r.json()["expires_in"] == 15 * 60

    cookie = r.cookies.get("refresh_token")
    assert cookie, "o refresh precisa vir em cookie"
    bruto = r.headers["set-cookie"]
    assert "HttpOnly" in bruto
    assert "SameSite=lax" in bruto.lower() or "samesite=lax" in bruto.lower()
    # O cookie só vale na rota de auth — nenhuma outra requisição o carrega.
    assert "Path=/api/auth" in bruto


@pytest.mark.asyncio
async def test_email_e_normalizado(client: AsyncClient) -> None:
    """Teste.X@Exemplo.com e teste.x@exemplo.com são a mesma conta."""
    await registrar(client, "caixa")

    repetido = await client.post(
        "/api/auth/register", json={**credenciais("caixa"), "email": "TESTE.CAIXA@EXEMPLO.COM"}
    )
    assert repetido.status_code == 409

    # E dá para entrar com o e-mail escrito de outro jeito.
    entrou = await client.post(
        "/api/auth/login",
        json={"email": "TESTE.CAIXA@exemplo.com", "password": "senha-bem-grande"},
    )
    assert entrou.status_code == 200


@pytest.mark.asyncio
async def test_login_com_senha_errada_nao_diz_qual_campo_falhou(client: AsyncClient) -> None:
    await registrar(client, "senha")
    c = credenciais("senha")

    errada = await client.post(
        "/api/auth/login", json={"email": c["email"], "password": "outra-senha-bem-grande"}
    )
    inexistente = await client.post(
        "/api/auth/login", json={"email": "ninguem@exemplo.com", "password": "qualquer-coisa-aqui"}
    )
    assert errada.status_code == inexistente.status_code == 401
    assert errada.json()["detail"] == inexistente.json()["detail"]


@pytest.mark.asyncio
async def test_senha_curta_e_recusada(client: AsyncClient) -> None:
    r = await client.post(
        "/api/auth/register", json={**credenciais("curta"), "password": "1234567"}
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_me_exige_token(client: AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (
        await client.get("/api/auth/me", headers={"Authorization": "Bearer nada"})
    ).status_code == 401

    token = await registrar(client, "me")
    r = await client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["email"] == "teste.me@exemplo.com"
    assert "password_hash" not in r.text


@pytest.mark.asyncio
async def test_token_expirado_devolve_401_e_refresh_renova(client: AsyncClient) -> None:
    await registrar(client, "exp")
    s = get_settings()

    # Um access já vencido, assinado com a mesma chave.
    vencido = jwt.encode(
        {
            "sub": "1",
            "type": "access",
            "jti": "x",
            "iat": int((datetime.now(UTC) - timedelta(hours=2)).timestamp()),
            "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
        },
        s.jwt_secret,
        algorithm="HS256",
    )
    assert (await client.get("/api/auth/me", headers=auth(vencido))).status_code == 401

    # O cookie de refresh ficou no client; renovar devolve um access que funciona.
    novo = await client.post("/api/auth/refresh")
    assert novo.status_code == 200, novo.text
    assert (
        await client.get("/api/auth/me", headers=auth(novo.json()["access_token"]))
    ).status_code == 200


@pytest.mark.asyncio
async def test_refresh_usado_nao_serve_de_novo(client: AsyncClient) -> None:
    """Rotação: o refresh antigo é revogado assim que vira um novo."""
    await registrar(client, "rot")
    antigo = client.cookies.get("refresh_token")
    assert antigo

    assert (await client.post("/api/auth/refresh")).status_code == 200

    client.cookies.set("refresh_token", antigo, path="/api/auth")
    reusado = await client.post("/api/auth/refresh")
    assert reusado.status_code == 401
    assert "Entre de novo" in reusado.json()["detail"]


@pytest.mark.asyncio
async def test_logout_revoga_de_verdade(client: AsyncClient) -> None:
    await registrar(client, "out")
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.post("/api/auth/refresh")).status_code == 401


@pytest.mark.asyncio
async def test_refresh_nao_vale_como_access(client: AsyncClient) -> None:
    """Token de refresh é longo de propósito; aceitá-lo como access anularia isso."""
    await registrar(client, "tipo")
    refresh, _ = criar_token(1, "refresh")
    assert (await client.get("/api/auth/me", headers=auth(refresh))).status_code == 401


@pytest.mark.asyncio
async def test_token_assinado_com_outra_chave_e_rejeitado(client: AsyncClient) -> None:
    payload: dict[str, Any] = {
        "sub": "1",
        "type": "access",
        "jti": "y",
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    forjado = jwt.encode(payload, "uma-chave-completamente-diferente-32b", algorithm="HS256")
    assert (await client.get("/api/auth/me", headers=auth(forjado))).status_code == 401
