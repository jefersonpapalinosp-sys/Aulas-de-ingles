"""Rotas do parceiro de conversa (contrato do IA-45).

Três regras valem em todas elas:

Posse no `WHERE`, não em `if`. Um diálogo de outra conta responde 404, nunca
403 — a resposta não revela que ele existe.

Idempotência declarada. A criação pela `operation_key`, o turno pelo par
`(dialogue_id, position)`. Reenviar devolve o que já existe, sem segunda
cobrança de cota nem segundo job.

Modo com IA desligado responde `409 assist_disabled`, cota esgotada responde
`429`, e provedor fora do ar **não** vira erro: o turno é fechado com o roteiro
e `fallback=true`, porque o aluno precisa poder continuar a conversa.
"""

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.concurrency import require_idempotency_key
from app.api.deps import UsuarioAtual
from app.api.errors import IDEMPOTENCY_KEY_RESPONSES
from app.core.config import get_settings
from app.db.models import DialogueTurn, Lesson, SpeakingAttempt, SpeakingDialogue
from app.db.session import get_session
from app.schemas.assist import HumanRatingIn
from app.schemas.dialogue import (
    DialogueCreateIn,
    DialogueHintOut,
    DialogueOut,
    DialogueTurnAcceptedOut,
    DialogueTurnOut,
    TurnTextIn,
)
from app.services import dialogue as dialogue_service
from app.services.assist_quota import QuotaExceeded
from app.services.audio_inspection import inspect_audio
from app.services.audio_storage import AudioStorage, normalized_mime_type
from app.services.audio_upload import read_audio
from app.services.publication import lock_publication, published_lesson_ids

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/speaking/dialogues", tags=["speaking"])


def _turn_out(turn: DialogueTurn) -> DialogueTurnOut:
    return DialogueTurnOut(
        position=turn.position,
        role=turn.role,
        input_kind=turn.input_kind,
        state=turn.state,
        transcript=turn.transcript,
        checks=dict(turn.checks or {}),
        hints=[DialogueHintOut.model_validate(hint) for hint in (turn.hints or [])],
        partner_text=turn.partner_text,
        confidence=turn.confidence,
        fallback=turn.fallback,
        error_code=turn.error_code,
        human_rating=turn.human_rating,
        job_id=turn.transcription_job_id,
        created_at=turn.created_at,
        completed_at=turn.completed_at,
    )


def _remaining(dialogue: SpeakingDialogue, turns: list[DialogueTurn]) -> int:
    usados = sum(1 for turn in turns if turn.role == "student")
    return max(0, dialogue.turn_limit - usados)


def _dialogue_out(dialogue: SpeakingDialogue, turns: list[DialogueTurn]) -> DialogueOut:
    ordenados = sorted(turns, key=lambda turn: turn.position)
    return DialogueOut(
        id=dialogue.id,
        lesson_id=dialogue.lesson_id,
        mode=dialogue.mode,
        state=dialogue.state,
        partner_speaker=dialogue.partner_speaker,
        turn_limit=dialogue.turn_limit,
        turns_remaining=_remaining(dialogue, ordenados),
        provider_name=dialogue.provider_name,
        rubric_version=dialogue.rubric_version,
        started_at=dialogue.started_at,
        ended_at=dialogue.ended_at,
        turns=[_turn_out(turn) for turn in ordenados],
    )


async def _owned_dialogue(
    session: AsyncSession, dialogue_id: int, user_id: int, *, lock: bool = False
) -> SpeakingDialogue:
    query = select(SpeakingDialogue).where(
        SpeakingDialogue.id == dialogue_id,
        # Posse no WHERE: diálogo alheio não existe para esta conta.
        SpeakingDialogue.user_id == user_id,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    dialogue = (await session.execute(query)).scalar_one_or_none()
    if dialogue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diálogo não existe.")
    return dialogue


async def _turns(session: AsyncSession, dialogue_id: int) -> list[DialogueTurn]:
    return list(
        (
            await session.execute(
                select(DialogueTurn)
                .where(DialogueTurn.dialogue_id == dialogue_id)
                .order_by(DialogueTurn.position)
            )
        ).scalars()
    )


async def _owned_turn(
    session: AsyncSession, dialogue: SpeakingDialogue, position: int
) -> DialogueTurn:
    turn = (
        await session.execute(
            select(DialogueTurn).where(
                DialogueTurn.dialogue_id == dialogue.id,
                DialogueTurn.position == position,
            )
        )
    ).scalar_one_or_none()
    if turn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno não existe.")
    return turn


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


@router.post("", response_model=DialogueOut, status_code=status.HTTP_201_CREATED)
async def criar_dialogo(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[DialogueCreateIn, Body()],
    response: Response,
) -> DialogueOut:
    _private(response)
    require_idempotency_key(corpo.operation_key)
    await lock_publication(session)
    lesson = (
        await session.execute(
            select(Lesson).where(
                Lesson.id == corpo.lesson_id,
                Lesson.id.in_(published_lesson_ids()),
            )
        )
    ).scalar_one_or_none()
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aula não existe.")
    try:
        dialogue, _ = await dialogue_service.create_dialogue(
            session,
            usuario,
            lesson,
            mode=corpo.mode,
            operation_key=str(corpo.operation_key or uuid4()),
            partner_speaker=corpo.partner_speaker,
        )
    except dialogue_service.DialogueUnavailable as error:
        # 409 e não 503: não é indisponibilidade momentânea, é modo desligado
        # nesta instalação. O cliente deve oferecer o Roteiro.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "assist_disabled", "mode": corpo.mode},
        ) from error
    await session.commit()
    return _dialogue_out(dialogue, await _turns(session, dialogue.id))


@router.get("/{dialogue_id}", response_model=DialogueOut)
async def obter_dialogo(
    dialogue_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> DialogueOut:
    _private(response)
    dialogue = await _owned_dialogue(session, dialogue_id, usuario.id)
    return _dialogue_out(dialogue, await _turns(session, dialogue.id))


async def _admit(
    session: AsyncSession,
    dialogue: SpeakingDialogue,
    position: int,
    *,
    input_kind: str,
    idempotency_key: str,
    transcript: str | None = None,
    speaking_attempt_id: int | None = None,
) -> DialogueTurnAcceptedOut:
    """Admite o turno e, no Roteiro, já o fecha.

    O Roteiro não enfileira: ele não chama provedor e não pode depender do
    worker estar de pé — é justamente o modo que precisa sobreviver a isso.
    """
    try:
        turn, job = await dialogue_service.admit_turn(
            session,
            dialogue,
            position,
            input_kind=input_kind,  # type: ignore[arg-type]
            idempotency_key=idempotency_key,
            transcript=transcript,
            speaking_attempt_id=speaking_attempt_id,
        )
    except dialogue_service.TurnLimitReached as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "dialogue_turn_limit", "turn_limit": error.limit},
        ) from error
    except QuotaExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "assist_quota_exceeded"},
        ) from error

    if dialogue.mode == "script" and turn.state == "pending":
        brief = await dialogue_service.brief_for_lesson(
            session,
            (
                await session.execute(select(Lesson).where(Lesson.id == dialogue.lesson_id))
            ).scalar_one(),
        )
        await dialogue_service.resolve_turn(
            session, turn, dialogue, brief, transcript or (turn.transcript or "")
        )
    await session.commit()
    return DialogueTurnAcceptedOut(
        position=turn.position,
        state=turn.state,
        job_id=job.id if job else None,
        turns_remaining=_remaining(dialogue, await _turns(session, dialogue.id)),
    )


@router.post(
    "/{dialogue_id}/turns/{position}/text",
    response_model=DialogueTurnAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses=IDEMPOTENCY_KEY_RESPONSES,
)
async def turno_por_texto(
    dialogue_id: int,
    position: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[TurnTextIn, Body()],
    response: Response,
) -> DialogueTurnAcceptedOut:
    _private(response)
    require_idempotency_key(corpo.idempotency_key)
    dialogue = await _owned_dialogue(session, dialogue_id, usuario.id, lock=True)
    return await _admit(
        session,
        dialogue,
        position,
        input_kind="text",
        idempotency_key=str(corpo.idempotency_key or uuid4()),
        transcript=corpo.text,
    )


@router.put(
    "/{dialogue_id}/turns/{position}/audio",
    response_model=DialogueTurnAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def turno_por_audio(
    dialogue_id: int,
    position: int,
    request: Request,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DialogueTurnAcceptedOut:
    settings = get_settings()
    mime_type = normalized_mime_type(request.headers.get("content-type"))
    if mime_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formato de áudio não suportado.",
        )
    dialogue = await _owned_dialogue(session, dialogue_id, usuario.id)
    # Não retém conexão nem lock durante recepção lenta — mesma regra do
    # shadowing. Só leituras até aqui.
    await session.commit()
    data = await read_audio(request, settings.speaking_max_bytes)
    duration_ms = await inspect_audio(data, mime_type)

    dialogue = await _owned_dialogue(session, dialogue_id, usuario.id, lock=True)
    existente = (
        await session.execute(
            select(DialogueTurn).where(
                DialogueTurn.dialogue_id == dialogue.id,
                DialogueTurn.position == position,
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        # Reenvio do mesmo turno: nada de segundo áudio nem segunda cobrança.
        return DialogueTurnAcceptedOut(
            position=existente.position,
            state=existente.state,
            job_id=existente.transcription_job_id,
            turns_remaining=_remaining(dialogue, await _turns(session, dialogue.id)),
        )

    storage = AudioStorage(settings.speaking_storage_dir)
    key = storage.save(data, mime_type)
    attempt = SpeakingAttempt(
        user_id=usuario.id,
        transcript_cue_id=None,
        # `origin='dialogue'`: áudio de turno não é tentativa de shadowing e
        # não aparece nas listas daquele contrato.
        origin="dialogue",
        duration_ms=duration_ms,
        status="ready",
        storage_key=key,
        mime_type=mime_type,
        file_size=len(data),
        integrity_state="verified",
    )
    session.add(attempt)
    await session.flush()
    return await _admit(
        session,
        dialogue,
        position,
        input_kind="audio",
        idempotency_key=f"dialogue-{dialogue.id}-{position}",
        speaking_attempt_id=attempt.id,
    )


@router.get("/{dialogue_id}/turns/{position}", response_model=DialogueTurnOut)
async def obter_turno(
    dialogue_id: int,
    position: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> DialogueTurnOut:
    _private(response)
    dialogue = await _owned_dialogue(session, dialogue_id, usuario.id)
    return _turn_out(await _owned_turn(session, dialogue, position))


@router.put("/{dialogue_id}/turns/{position}/rating", response_model=DialogueTurnOut)
async def avaliar_turno(
    dialogue_id: int,
    position: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[HumanRatingIn, Body()],
    response: Response,
) -> DialogueTurnOut:
    """A avaliação humana é o único campo do turno que a API altera.

    É a matéria-prima do gate do IA-48, e os grants por coluna do DB-45
    garantem isso no banco, não só aqui.
    """
    _private(response)
    dialogue = await _owned_dialogue(session, dialogue_id, usuario.id)
    turn = await _owned_turn(session, dialogue, position)
    turn.human_rating = corpo.rating
    await session.commit()
    return _turn_out(turn)


@router.delete("/{dialogue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_dialogo(
    dialogue_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> Response:
    """Apaga o diálogo e, por cascata do PostgreSQL, seus turnos.

    O áudio segue a política de speaking: o arquivo sai pelo caminho de
    exclusão de gravação, não daqui, para não criar um segundo lugar que
    remove bytes do aluno.
    """
    dialogue = await _owned_dialogue(session, dialogue_id, usuario.id)
    await session.delete(dialogue)
    await session.commit()
    logger.info("dialogue_deleted", extra={"dialogue_id": dialogue_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
