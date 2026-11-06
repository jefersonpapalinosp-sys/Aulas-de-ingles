"""Listening independente: links externos e marcações do próprio aluno."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.core.config import get_settings
from app.db.models import ListeningOperation, ListeningProgress, ListeningResource, User
from app.db.session import get_session
from app.schemas.listening import (
    ListeningConfigOut,
    ListeningProgressIn,
    ListeningProgressOut,
    ListeningResourceOut,
)

router = APIRouter(tags=["listening"])
Session = Annotated[AsyncSession, Depends(get_session)]


def require_enabled() -> None:
    if not get_settings().listening_enabled:
        raise HTTPException(404, "Listening rápido ainda não está disponível.")


@router.get("/listening/config", response_model=ListeningConfigOut)
async def config(user: UsuarioAtual) -> ListeningConfigOut:
    return ListeningConfigOut(enabled=get_settings().listening_enabled)


@router.get("/listening/resources", response_model=list[ListeningResourceOut])
async def resources(user: UsuarioAtual, session: Session) -> list[ListeningResource]:
    require_enabled()
    return list(
        await session.scalars(
            select(ListeningResource).order_by(ListeningResource.position, ListeningResource.slug)
        )
    )


@router.get("/listening/resources/{slug}", response_model=ListeningResourceOut)
async def resource(slug: str, user: UsuarioAtual, session: Session) -> ListeningResource:
    require_enabled()
    row = await session.get(ListeningResource, slug)
    if row is None:
        raise HTTPException(404, "Atividade não encontrada.")
    return row


@router.get("/me/listening/progress", response_model=list[ListeningProgressOut])
async def progress(user: UsuarioAtual, session: Session) -> list[ListeningProgress]:
    require_enabled()
    return list(
        await session.scalars(
            select(ListeningProgress)
            .where(ListeningProgress.user_id == user.id)
            .order_by(ListeningProgress.resource_slug)
        )
    )


@router.put("/me/listening/progress/{slug}", response_model=ListeningProgressOut)
async def update_progress(
    slug: str,
    body: ListeningProgressIn,
    user: UsuarioAtual,
    session: Session,
) -> ListeningProgressOut:
    require_enabled()
    user_id = user.id
    # Também serializa com a exclusão da conta e protege a primeira inserção.
    owner = await session.scalar(select(User.id).where(User.id == user_id).with_for_update())
    if owner is None:
        raise HTTPException(401, "Conta inexistente.")
    operation_key = str(body.operation_key)
    receipt = await session.scalar(
        select(ListeningOperation).where(
            ListeningOperation.user_id == user_id,
            ListeningOperation.operation_key == operation_key,
        )
    )
    if receipt is not None:
        if (receipt.resource_slug, receipt.state, receipt.expected_revision) != (
            slug,
            body.state,
            body.expected_revision,
        ):
            raise HTTPException(409, "Esta operação já foi usada com outros dados.")
        return ListeningProgressOut.model_validate(receipt)
    if await session.get(ListeningResource, slug) is None:
        raise HTTPException(404, "Atividade não encontrada.")
    row = await session.scalar(
        select(ListeningProgress).where(
            ListeningProgress.user_id == user_id,
            ListeningProgress.resource_slug == slug,
        )
    )
    if (row.revision if row else 0) != body.expected_revision:
        raise HTTPException(
            409, "O progresso mudou em outra aba. Atualize antes de marcar novamente."
        )
    now = datetime.now(UTC)
    revision = body.expected_revision + 1
    if row is None:
        row = ListeningProgress(user_id=user_id, resource_slug=slug)
        session.add(row)
    row.state, row.revision, row.updated_at = body.state, revision, now
    session.add(
        ListeningOperation(
            user_id=user_id,
            operation_key=operation_key,
            resource_slug=slug,
            state=body.state,
            expected_revision=body.expected_revision,
            revision=revision,
            updated_at=now,
        )
    )
    await session.commit()
    return ListeningProgressOut.model_validate(row)
