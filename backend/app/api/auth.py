"""Autenticação com hashes limitados e rotação atômica, sem guardar tokens em claro."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.core.config import get_settings
from app.core.security import TokenInvalido, conferir_senha, criar_token, hash_senha, ler_token
from app.db.models import RefreshSession, User
from app.db.session import get_session
from app.schemas.auth import LoginIn, RegistroIn, TokenOut, UsuarioOut
from app.services.auth_limits import password_work, rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "refresh_token"
REFRESH_GRACE_SECONDS = 10
_DUMMY_HASH = hash_senha("dummy-not-a-user-password")


def _normalizar_email(email: str) -> str:
    return email.strip().lower()


def _tokens(resposta: Response, sessao: RefreshSession) -> TokenOut:
    settings = get_settings()
    access, _ = criar_token(sessao.user_id, "access")
    refresh, _ = criar_token(
        sessao.user_id,
        "refresh",
        sessao.jti,
        issued_at=sessao.created_at,
        expires_at=sessao.expires_at,
    )
    resposta.set_cookie(
        COOKIE,
        refresh,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/auth",
        max_age=max(0, int((sessao.expires_at - datetime.now(UTC)).total_seconds())),
    )
    return TokenOut(access_token=access, expires_in=settings.access_token_minutes * 60)


def _new_session(user_id: int, family: str | None = None) -> RefreshSession:
    now = datetime.now(UTC)
    jti = uuid4().hex
    return RefreshSession(
        user_id=user_id,
        jti=jti,
        family_id=family or jti,
        created_at=now,
        expires_at=now + timedelta(days=get_settings().refresh_token_days),
    )


async def _abrir_sessao(session: AsyncSession, usuario: User, resposta: Response) -> TokenOut:
    sessao = _new_session(usuario.id)
    session.add(sessao)
    await session.commit()
    return _tokens(resposta, sessao)


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def registrar(
    corpo: RegistroIn,
    request: Request,
    resposta: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenOut:
    email = _normalizar_email(corpo.email)
    await rate_limit(session, request, email)
    password_hash = await password_work(hash_senha, corpo.password)
    user_id = (
        await session.execute(
            insert(User)
            .values(
                email=email,
                password_hash=password_hash,
                display_name=corpo.display_name.strip(),
            )
            .on_conflict_do_nothing(index_elements=[User.email])
            .returning(User.id)
        )
    ).scalar_one_or_none()
    if user_id is None:
        raise HTTPException(409, "Já existe conta com esse e-mail.")
    usuario = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
    return await _abrir_sessao(session, usuario, resposta)


@router.post("/login", response_model=TokenOut)
async def entrar(
    corpo: LoginIn,
    request: Request,
    resposta: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenOut:
    email = _normalizar_email(corpo.email)
    await rate_limit(session, request, email)
    usuario = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    password_hash = usuario.password_hash if usuario else _DUMMY_HASH
    await session.commit()
    valid = await password_work(conferir_senha, corpo.password, password_hash)
    if usuario is None or not valid:
        raise HTTPException(401, "E-mail ou senha incorretos.")
    return await _abrir_sessao(session, usuario, resposta)


async def _locked_cookie(session: AsyncSession, bruto: str) -> RefreshSession | None:
    payload = ler_token(bruto, "refresh")
    user_id = int(payload["sub"])
    await session.execute(select(func.pg_advisory_xact_lock(3802, user_id)))
    return (
        await session.execute(
            select(RefreshSession)
            .where(
                RefreshSession.jti == payload["jti"],
                RefreshSession.user_id == user_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()


@router.post("/refresh", response_model=TokenOut)
async def renovar(
    request: Request, resposta: Response, session: Annotated[AsyncSession, Depends(get_session)]
) -> TokenOut:
    bruto = request.cookies.get(COOKIE)
    if not bruto:
        raise HTTPException(401, "Sem refresh token.")
    try:
        current = await _locked_cookie(session, bruto)
    except TokenInvalido as error:
        raise HTTPException(401, "Refresh token inválido.") from error
    now = datetime.now(UTC)
    if current is None or current.expires_at <= now:
        raise HTTPException(401, "Sessão encerrada. Entre de novo.")
    if current.revoked_at is not None:
        if (
            not current.successor_jti
            or (now - current.revoked_at).total_seconds() > REFRESH_GRACE_SECONDS
        ):
            raise HTTPException(401, "Sessão encerrada. Entre de novo.")
        successor = (
            await session.execute(
                select(RefreshSession).where(
                    RefreshSession.jti == current.successor_jti,
                    RefreshSession.user_id == current.user_id,
                    RefreshSession.family_id == current.family_id,
                )
            )
        ).scalar_one_or_none()
        if successor is None or successor.revoked_at is not None or successor.expires_at <= now:
            raise HTTPException(401, "Sessão encerrada. Entre de novo.")
    elif (
        current.family_id != current.jti
        and (now - current.created_at).total_seconds() <= REFRESH_GRACE_SECONDS
    ):
        # Coalesce inclusive pedidos que já receberam o cookie novo.
        successor = current
    else:
        successor = _new_session(current.user_id, current.family_id)
        current.revoked_at = now
        current.successor_jti = successor.jti
        session.add(successor)
    await session.commit()
    return _tokens(resposta, successor)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def sair(
    request: Request, resposta: Response, session: Annotated[AsyncSession, Depends(get_session)]
) -> None:
    bruto = request.cookies.get(COOKIE)
    if bruto:
        try:
            current = await _locked_cookie(session, bruto)
            if current is not None:
                await session.execute(
                    update(RefreshSession)
                    .where(
                        RefreshSession.user_id == current.user_id,
                        RefreshSession.family_id == current.family_id,
                    )
                    .values(revoked_at=datetime.now(UTC), successor_jti=None)
                )
                await session.commit()
        except TokenInvalido:
            pass
    resposta.delete_cookie(
        COOKIE, path="/api/auth", secure=get_settings().cookie_secure, httponly=True, samesite="lax"
    )


@router.get("/me", response_model=UsuarioOut)
async def quem_sou_eu(usuario: UsuarioAtual) -> User:
    return usuario
