"""Registro, login, refresh e logout."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.core.config import Settings, get_settings
from app.core.security import (
    TokenInvalido,
    conferir_senha,
    criar_token,
    hash_senha,
    ler_token,
)
from app.db.models import RefreshSession, User
from app.db.session import get_session
from app.schemas.auth import LoginIn, RegistroIn, TokenOut, UsuarioOut

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE = "refresh_token"
CREDENCIAL_INVALIDA = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha incorretos."
)


def _normalizar_email(email: str) -> str:
    return email.strip().lower()


async def _abrir_sessao(session: AsyncSession, usuario: User, resposta: Response) -> TokenOut:
    """Emite o par de tokens e grava a sessão de refresh."""
    s = get_settings()
    access, _ = criar_token(usuario.id, "access")
    refresh, jti = criar_token(usuario.id, "refresh")

    session.add(
        RefreshSession(
            user_id=usuario.id,
            jti=jti,
            expires_at=datetime.now(UTC) + timedelta(days=s.refresh_token_days),
        )
    )
    await session.commit()

    resposta.set_cookie(
        COOKIE,
        refresh,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        max_age=s.refresh_token_days * 24 * 3600,
        # Só a rota de refresh precisa do cookie — nenhuma outra o recebe.
        path="/api/auth",
    )
    return TokenOut(access_token=access, expires_in=s.access_token_minutes * 60)


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def registrar(
    corpo: RegistroIn,
    resposta: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenOut:
    email = _normalizar_email(corpo.email)
    existe = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existe is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Já existe conta com esse e-mail."
        )
    usuario = User(
        email=email,
        password_hash=hash_senha(corpo.password),
        display_name=corpo.display_name.strip(),
    )
    session.add(usuario)
    await session.flush()
    return await _abrir_sessao(session, usuario, resposta)


@router.post("/login", response_model=TokenOut)
async def entrar(
    corpo: LoginIn,
    resposta: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenOut:
    usuario = (
        await session.execute(select(User).where(User.email == _normalizar_email(corpo.email)))
    ).scalar_one_or_none()
    # Mesma mensagem para e-mail inexistente e senha errada: dizer qual dos
    # dois falhou entrega quais e-mails têm conta.
    if usuario is None or not conferir_senha(corpo.password, usuario.password_hash):
        raise CREDENCIAL_INVALIDA
    return await _abrir_sessao(session, usuario, resposta)


@router.post("/refresh", response_model=TokenOut)
async def renovar(
    request: Request,
    resposta: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenOut:
    """Troca o refresh por um access novo. O refresh antigo é revogado."""
    bruto = request.cookies.get(COOKIE)
    if not bruto:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sem refresh token.")
    try:
        payload = ler_token(bruto, "refresh")
    except TokenInvalido as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido."
        ) from e

    sessao = (
        await session.execute(select(RefreshSession).where(RefreshSession.jti == payload["jti"]))
    ).scalar_one_or_none()
    if sessao is None or sessao.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão encerrada. Entre de novo."
        )

    usuario = (
        await session.execute(select(User).where(User.id == sessao.user_id))
    ).scalar_one_or_none()
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Conta não existe.")

    # Rotação: um refresh usado não serve de novo.
    sessao.revoked_at = datetime.now(UTC)
    await session.flush()
    _ = settings
    return await _abrir_sessao(session, usuario, resposta)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def sair(
    request: Request,
    resposta: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Revoga a sessão de refresh e apaga o cookie."""
    bruto = request.cookies.get(COOKIE)
    if bruto:
        try:
            payload = ler_token(bruto, "refresh")
            await session.execute(
                update(RefreshSession)
                .where(RefreshSession.jti == payload["jti"])
                .values(revoked_at=datetime.now(UTC))
            )
            await session.commit()
        except TokenInvalido:
            pass  # cookie inválido: nada a revogar, mas sair tem que funcionar
    resposta.delete_cookie(COOKIE, path="/api/auth")


@router.get("/me", response_model=UsuarioOut)
async def quem_sou_eu(usuario: UsuarioAtual) -> User:
    return usuario
