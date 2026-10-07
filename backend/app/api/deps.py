"""Dependências de autenticação."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenInvalido, ler_token
from app.db.models import User
from app.db.session import get_session

NAO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Não autenticado.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def usuario_atual(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Lê o access token do header Authorization e devolve o dono dele.

    O access token vive na memória do frontend, não em cookie: cookie que o
    navegador manda sozinho em toda requisição é o que abre espaço para CSRF.
    Quem fica em cookie httpOnly é só o refresh, que só serve numa rota.
    """
    cabecalho = request.headers.get("Authorization", "")
    if not cabecalho.startswith("Bearer "):
        raise NAO_AUTENTICADO
    try:
        payload = ler_token(cabecalho.removeprefix("Bearer "), "access")
    except TokenInvalido as e:
        raise NAO_AUTENTICADO from e

    usuario = (
        await session.execute(select(User).where(User.id == int(payload["sub"])))
    ).scalar_one_or_none()
    if usuario is None:
        raise NAO_AUTENTICADO
    return usuario


UsuarioAtual = Annotated[User, Depends(usuario_atual)]
