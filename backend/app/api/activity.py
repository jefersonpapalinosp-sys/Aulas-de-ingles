"""Tempo ativo ancorado no servidor. Primeiro intervalo recebido ocupa o tempo."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.models import (
    StudyActiveInterval,
    StudyActivityEvent,
    StudyActivitySession,
    User,
)
from app.db.session import get_session
from app.schemas.activity import (
    ActivityEventIn,
    ActivityEventOut,
    ActivitySessionIn,
    ActivitySessionOut,
)
from app.services.publication import require_published_lesson

router = APIRouter(prefix="/me/activity", tags=["activity"])


def uncovered(
    start: datetime, end: datetime, occupied: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    """Subtrai interseções, sem arredondamento que possa duplicar segundos."""
    cursor = start
    result = []
    for left, right in sorted(occupied):
        if left > cursor:
            result.append((cursor, min(left, end)))
        cursor = max(cursor, right)
        if cursor >= end:
            break
    if cursor < end:
        result.append((cursor, end))
    return result


@router.post("/sessions", response_model=ActivitySessionOut)
async def start_session(
    body: ActivitySessionIn,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ActivitySessionOut:
    await session.execute(select(User.id).where(User.id == usuario.id).with_for_update())
    existing = await session.get(StudyActivitySession, str(body.session_id))
    if existing is not None:
        if existing.user_id != usuario.id or existing.lesson_id != body.lesson_id:
            raise HTTPException(409, detail="Identificador de sessão já utilizado.")
        return ActivitySessionOut(
            session_id=existing.id, started_at=existing.started_at, server_now=datetime.now(UTC)
        )
    await require_published_lesson(session, body.lesson_id)
    activity = StudyActivitySession(
        id=str(body.session_id),
        user_id=usuario.id,
        lesson_id=body.lesson_id,
        started_at=datetime.now(UTC),
    )
    session.add(activity)
    await session.commit()
    return ActivitySessionOut(
        session_id=activity.id, started_at=activity.started_at, server_now=datetime.now(UTC)
    )


@router.post("/events", response_model=ActivityEventOut)
async def record_event(
    body: ActivityEventIn,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ActivityEventOut:
    # Serializa deduplicação e subtração global por usuário, não só por aula/aba.
    await session.execute(select(User.id).where(User.id == usuario.id).with_for_update())
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    existing = (
        await session.execute(
            select(StudyActivityEvent).where(
                StudyActivityEvent.user_id == usuario.id,
                StudyActivityEvent.operation_key == str(body.operation_key),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.fingerprint != fingerprint:
            raise HTTPException(
                409, detail="Identificador de evento reutilizado com outro conteúdo."
            )
        return ActivityEventOut(
            operation_key=existing.operation_key, credited_ms=existing.credited_ms
        )
    activity = await session.get(StudyActivitySession, str(body.session_id))
    if activity is None or activity.user_id != usuario.id:
        raise HTTPException(404, detail="Sessão de atividade não existe.")
    now = datetime.now(UTC)
    if activity.started_at < now - timedelta(days=7):
        raise HTTPException(
            410, detail="Janela de envio de atividade expirada; tempo não contabilizado."
        )
    end = activity.started_at + timedelta(milliseconds=body.end_offset_ms)
    start = end - timedelta(milliseconds=body.duration_ms)
    if start < activity.started_at or end > now + timedelta(seconds=2):
        raise HTTPException(422, detail="Intervalo fora da janela de tempo do servidor.")
    occupied = (
        await session.execute(
            select(StudyActiveInterval.starts_at, StudyActiveInterval.ends_at)
            .where(
                StudyActiveInterval.user_id == usuario.id,
                StudyActiveInterval.ends_at > start,
                StudyActiveInterval.starts_at < end,
            )
            .order_by(StudyActiveInterval.starts_at)
        )
    ).all()
    pieces = uncovered(start, end, [(row[0], row[1]) for row in occupied])
    credited = min(
        body.duration_ms, int(sum((right - left).total_seconds() * 1000 for left, right in pieces))
    )
    event = StudyActivityEvent(
        user_id=usuario.id,
        session_id=activity.id,
        operation_key=str(body.operation_key),
        fingerprint=fingerprint,
        duration_ms=body.duration_ms,
        credited_ms=credited,
    )
    session.add(event)
    await session.flush()
    for left, right in pieces:
        session.add(
            StudyActiveInterval(
                event_id=event.id,
                user_id=usuario.id,
                lesson_id=activity.lesson_id,
                starts_at=left,
                ends_at=right,
            )
        )
    await session.commit()
    return ActivityEventOut(operation_key=event.operation_key, credited_ms=credited)
