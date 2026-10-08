"""Retomada autenticada de áudio e vídeo entre dispositivos."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.models import LessonMedia, MediaProgress
from app.db.session import get_session
from app.schemas.progress import MediaPositionIn, MediaPositionOut

router = APIRouter(prefix="/media", tags=["media"])


async def _media(session: AsyncSession, media_id: int) -> LessonMedia:
    media = (
        await session.execute(select(LessonMedia).where(LessonMedia.id == media_id))
    ).scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mídia não existe.")
    return media


@router.get("/{media_id}/position", response_model=MediaPositionOut)
async def obter_posicao(
    media_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MediaPositionOut:
    await _media(session, media_id)
    progress = (
        await session.execute(
            select(MediaProgress).where(
                MediaProgress.user_id == usuario.id,
                MediaProgress.media_id == media_id,
            )
        )
    ).scalar_one_or_none()
    if progress is None:
        return MediaPositionOut(media_id=media_id, position_seconds=0, updated_at=None)
    return MediaPositionOut.model_validate(progress, from_attributes=True)


@router.put("/{media_id}/position", response_model=MediaPositionOut)
async def salvar_posicao(
    media_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[MediaPositionIn, Body()],
) -> MediaPositionOut:
    media = await _media(session, media_id)
    if media.duration_seconds is not None and corpo.position_seconds > media.duration_seconds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A posição ultrapassa a duração conhecida da mídia.",
        )
    progress = (
        await session.execute(
            select(MediaProgress).where(
                MediaProgress.user_id == usuario.id,
                MediaProgress.media_id == media_id,
            )
        )
    ).scalar_one_or_none()
    if progress is None:
        progress = MediaProgress(
            user_id=usuario.id,
            media_id=media_id,
            position_seconds=corpo.position_seconds,
        )
        session.add(progress)
    else:
        progress.position_seconds = corpo.position_seconds
    await session.commit()
    await session.refresh(progress)
    return MediaPositionOut.model_validate(progress, from_attributes=True)


@router.delete("/{media_id}/position", status_code=status.HTTP_204_NO_CONTENT)
async def limpar_posicao(
    media_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await _media(session, media_id)
    await session.execute(
        delete(MediaProgress).where(
            MediaProgress.user_id == usuario.id,
            MediaProgress.media_id == media_id,
        )
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
