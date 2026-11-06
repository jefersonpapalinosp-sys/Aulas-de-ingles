"""Histórico paginado e posição de áudio com revisão independente das respostas."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import UsuarioAtual
from app.api.listening import Session
from app.api.native_listening import owned, owner_lock, require_native, visible
from app.db.models import (
    NativeListeningPosition,
    NativeListeningResponse,
    NativeListeningSession,
    NativeListeningVersion,
)
from app.schemas.listening_history import (
    NativeHistoryItem,
    NativeHistoryOut,
    NativePositionIn,
    NativePositionOut,
)
from app.schemas.native_listening import NativeContent

router = APIRouter(prefix="/listening", tags=["native-listening"])


def position_out(session_id: int, row: NativeListeningPosition | None) -> NativePositionOut:
    return NativePositionOut(
        session_id=session_id,
        position_seconds=row.position_seconds if row else 0,
        revision=row.revision if row else 0,
        completed=row.completed if row else False,
        operation_key=row.operation_key if row else None,
        changed_at=row.changed_at if row else None,
        updated_at=row.updated_at if row else None,
    )


async def position_row(
    session: Session, session_id: int, user_id: int
) -> NativeListeningPosition | None:
    return await session.scalar(
        select(NativeListeningPosition).where(
            NativeListeningPosition.session_id == session_id,
            NativeListeningPosition.user_id == user_id,
        )
    )


@router.get("/sessions/{session_id}/position", response_model=NativePositionOut)
async def read_position(session_id: int, user: UsuarioAtual, session: Session) -> NativePositionOut:
    await owned(session, session_id, user.id)
    return position_out(session_id, await position_row(session, session_id, user.id))


@router.put("/sessions/{session_id}/position", response_model=NativePositionOut)
async def save_position(
    session_id: int,
    body: NativePositionIn,
    user: UsuarioAtual,
    session: Session,
) -> NativePositionOut:
    require_native()
    await owner_lock(session, user.id)
    practice = await owned(session, session_id, user.id)
    version = await session.get(NativeListeningVersion, practice.version_id)
    assert version is not None
    content = NativeContent.model_validate(version.content)
    if not visible(content):
        raise HTTPException(404, "Atividade indisponível.")
    now = datetime.now(UTC)
    if body.changed_at > now + timedelta(minutes=5):
        raise HTTPException(422, "Confira o relógio do dispositivo.")
    if body.position_seconds > content.audio_duration_seconds or (
        body.completed and body.position_seconds != 0
    ):
        raise HTTPException(422, "Posição incompatível com o áudio desta versão.")
    row = await position_row(session, session_id, user.id)
    fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    if row and row.operation_key == str(body.operation_key):
        if row.fingerprint != fingerprint:
            raise HTTPException(409, "Operação já utilizada com outra posição.")
        return position_out(session_id, row)
    if (row.revision if row else 0) != body.expected_revision:
        raise HTTPException(409, "A posição mudou em outra aba. Escolha qual manter.")
    if row is None:
        row = NativeListeningPosition(user_id=user.id, session_id=session_id)
        session.add(row)
    row.position_seconds, row.completed = body.position_seconds, body.completed
    row.revision = body.expected_revision + 1
    row.operation_key, row.fingerprint = str(body.operation_key), fingerprint
    row.changed_at, row.updated_at = body.changed_at, now
    await session.commit()
    return position_out(session_id, row)


@router.get("/history", response_model=NativeHistoryOut)
async def history(
    user: UsuarioAtual,
    session: Session,
    before: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    slug: Annotated[str | None, Query(max_length=100)] = None,
) -> NativeHistoryOut:
    require_native()
    filters = [NativeListeningSession.user_id == user.id]
    if slug is not None:
        filters.append(NativeListeningVersion.slug == slug)
    count, first, last = (
        await session.execute(
            select(
                func.count(),
                func.min(NativeListeningSession.created_at),
                func.max(NativeListeningSession.created_at),
            )
            .select_from(NativeListeningSession)
            .join(NativeListeningVersion)
            .where(*filters)
        )
    ).one()
    if before is not None:
        filters.append(NativeListeningSession.id < before)
    rows = (
        await session.execute(
            select(
                NativeListeningSession,
                NativeListeningVersion,
                NativeListeningPosition.position_seconds,
            )
            .join(NativeListeningVersion)
            .outerjoin(
                NativeListeningPosition,
                NativeListeningPosition.session_id == NativeListeningSession.id,
            )
            .where(*filters)
            .order_by(NativeListeningSession.id.desc())
            .limit(limit + 1)
        )
    ).all()
    page = rows[:limit]
    ids = [row[0].id for row in page]
    events: dict[int, list[NativeListeningResponse]] = {key: [] for key in ids}
    if ids:
        for event in await session.scalars(
            select(NativeListeningResponse)
            .where(
                NativeListeningResponse.user_id == user.id,
                NativeListeningResponse.session_id.in_(ids),
            )
            .order_by(NativeListeningResponse.revision)
        ):
            events[event.session_id].append(event)
    items = []
    for practice, version, position in page:
        content = NativeContent.model_validate(version.content)
        questions = {q.id: q for q in content.questions}
        first_answers: dict[str, bool] = {}
        latest: dict[str, bool] = {}
        support = False
        for event in events[practice.id]:
            payload = event.payload
            if payload["kind"] == "transcript":
                support = True
                continue
            key = payload["question_id"]
            correct = payload["kind"] == "answer" and set(payload["selected_ids"]) == set(
                questions[key].answer_ids
            )
            first_answers.setdefault(key, correct)
            latest[key] = correct
        items.append(
            NativeHistoryItem(
                session_id=practice.id,
                slug=content.slug,
                version=content.version,
                title=content.title,
                available=visible(content),
                started_at=practice.created_at,
                last_response_at=events[practice.id][-1].created_at
                if events[practice.id]
                else None,
                completed=len(first_answers) == len(questions),
                first_score=sum(first_answers.values()),
                latest_score=sum(latest.values()),
                answered=len(first_answers),
                total=len(questions),
                support_revealed=support,
                position_seconds=position or 0,
            )
        )
    return NativeHistoryOut(
        items=items,
        next_before=page[-1][0].id if len(rows) > limit else None,
        attempts=count,
        first_attempt_at=first,
        last_attempt_at=last,
    )
