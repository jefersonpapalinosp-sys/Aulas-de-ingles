"""Retomada por CAS. Concluir mantém tombstone para recusar gravações atrasadas."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.concurrency import conflict
from app.api.deps import UsuarioAtual
from app.db.models import LessonMedia, MediaProgress
from app.db.session import get_session
from app.schemas.progress import MediaPositionIn, MediaPositionOut
from app.services.publication import require_published_lesson

router = APIRouter(prefix="/media", tags=["media"])


async def _media(session: AsyncSession, media_id: int) -> LessonMedia:
    media = await session.get(LessonMedia, media_id)
    if media is None:
        raise HTTPException(404, detail="Mídia não existe.")
    return media


@router.get("/{media_id}/position", response_model=MediaPositionOut)
async def obter_posicao(
    media_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MediaPositionOut:
    media = await _media(session, media_id)
    progress = (
        await session.execute(
            select(MediaProgress).where(
                MediaProgress.user_id == usuario.id,
                MediaProgress.media_id == media_id,
            )
        )
    ).scalar_one_or_none()
    if progress is None:
        await require_published_lesson(session, media.lesson_id)
        return MediaPositionOut(
            media_id=media_id,
            position_seconds=0,
            updated_at=None,
            revision=0,
            completed=False,
            operation_key=None,
            changed_at=None,
        )
    return MediaPositionOut.model_validate(progress, from_attributes=True)


async def _save(
    session: AsyncSession, user_id: int, media_id: int, body: MediaPositionIn
) -> MediaPositionOut:
    media = await _media(session, media_id)
    # Clearing an existing personal position is not a new curricular activity.
    # Keep its revision/tombstone contract even after the source is archived.
    existing_reset = None
    if body.completed and body.position_seconds == 0:
        existing_reset = await session.scalar(
            select(MediaProgress.id).where(
                MediaProgress.user_id == user_id, MediaProgress.media_id == media_id
            )
        )
    if existing_reset is None:
        await require_published_lesson(session, media.lesson_id)
    now = datetime.now(UTC)
    if body.changed_at > now + timedelta(minutes=5):
        raise HTTPException(422, detail="Relógio adiantado. Confira a data deste dispositivo.")
    if body.completed and body.position_seconds != 0:
        raise HTTPException(422, detail="Conclusão deve zerar a posição.")
    if media.duration_seconds is not None and body.position_seconds > media.duration_seconds:
        raise HTTPException(422, detail="A posição ultrapassa a duração conhecida da mídia.")
    await session.execute(
        insert(MediaProgress)
        .values(user_id=user_id, media_id=media_id)
        .on_conflict_do_nothing(constraint="uq_media_progress_user_media")
    )
    progress = (
        await session.execute(
            select(MediaProgress)
            .where(
                MediaProgress.user_id == user_id,
                MediaProgress.media_id == media_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    if progress.operation_key == str(body.operation_key):
        if progress.fingerprint != fingerprint:
            raise conflict("media_operation_reused", {})
    elif progress.revision != body.expected_revision:
        raise conflict(
            "media_revision_conflict",
            MediaPositionOut.model_validate(progress, from_attributes=True).model_dump(mode="json"),
        )
    else:
        progress.position_seconds = body.position_seconds
        progress.completed = body.completed
        progress.changed_at = body.changed_at
        progress.operation_key = str(body.operation_key)
        progress.fingerprint = fingerprint
        progress.revision += 1
        progress.updated_at = now
    await session.commit()
    return MediaPositionOut.model_validate(progress, from_attributes=True)


@router.put("/{media_id}/position", response_model=MediaPositionOut)
async def salvar_posicao(
    media_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[MediaPositionIn, Body()],
) -> MediaPositionOut:
    return await _save(session, usuario.id, media_id, corpo)


@router.delete("/{media_id}/position", status_code=204)
async def limpar_posicao(
    media_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    expected_revision: Annotated[int, Query(ge=0)],
    operation_key: UUID,
    changed_at: AwareDatetime,
) -> Response:
    await _save(
        session,
        usuario.id,
        media_id,
        MediaPositionIn(
            position_seconds=0,
            completed=True,
            expected_revision=expected_revision,
            operation_key=operation_key,
            changed_at=changed_at,
        ),
    )
    return Response(status_code=204)
