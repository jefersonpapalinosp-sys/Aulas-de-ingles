"""Senha e token. Lógica pura, sem banco e sem HTTP.

Separado porque é o tipo de código que não se quer reimplementar em dois
lugares: um hash feito diferente em dois pontos é uma conta que não loga.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

# Parâmetros padrão do argon2-cffi seguem a recomendação do RFC 9106.
_hasher = PasswordHasher()

TipoToken = Literal["access", "refresh"]


class TokenInvalido(Exception):
    """Token ausente, expirado, adulterado ou do tipo errado."""


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def conferir_senha(senha: str, hash_guardado: str) -> bool:
    """Senha errada e hash corrompido dão o mesmo resultado: não entra."""
    try:
        _hasher.verify(hash_guardado, senha)
    except (VerificationError, InvalidHashError):
        return False
    return True


def precisa_rehash(hash_guardado: str) -> bool:
    """True quando o hash foi feito com parâmetros antigos."""
    return _hasher.check_needs_rehash(hash_guardado)


def criar_token(user_id: int, tipo: TipoToken, jti: str | None = None) -> tuple[str, str]:
    """Devolve (token, jti). O jti identifica a sessão de refresh no banco."""
    s = get_settings()
    agora = datetime.now(UTC)
    duracao = (
        timedelta(minutes=s.access_token_minutes)
        if tipo == "access"
        else timedelta(days=s.refresh_token_days)
    )
    identificador = jti or uuid4().hex
    payload = {
        "sub": str(user_id),
        "type": tipo,
        "jti": identificador,
        "iat": int(agora.timestamp()),
        "exp": int((agora + duracao).timestamp()),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256"), identificador


def ler_token(token: str, tipo_esperado: TipoToken) -> dict[str, Any]:
    """Valida assinatura, validade e tipo. Qualquer problema vira TokenInvalido."""
    try:
        payload: dict[str, Any] = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise TokenInvalido(str(e)) from e
    if payload.get("type") != tipo_esperado:
        # Um refresh não pode ser usado como access: é mais longo de propósito.
        raise TokenInvalido(f"esperava token do tipo {tipo_esperado}")
    return payload
