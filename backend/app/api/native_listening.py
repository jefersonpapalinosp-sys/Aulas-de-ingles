"""Listening próprio: versão fixa, correção no servidor e recibos por aluno."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import UsuarioAtual
from app.api.listening import Session
from app.core.config import get_settings
from app.db.models import (
    NativeListeningResponse,
    NativeListeningSession,
    NativeListeningVersion,
    User,
)
from app.db.native_listening_seed import media_path
from app.schemas.native_listening import (
    NativeActivityOut,
    NativeConfigOut,
    NativeContent,
    NativeFeedbackOut,
    NativeQuestion,
    NativeResponseIn,
    NativeSessionOut,
    NativeStartIn,
)

router = APIRouter(prefix="/listening", tags=["native-listening"])


@router.get("/native-config", response_model=NativeConfigOut)
async def config(user: UsuarioAtual) -> NativeConfigOut:
    return NativeConfigOut(
        enabled=get_settings().listening_native_enabled, preview=preview_allowed()
    )


def preview_allowed() -> bool:
    settings = get_settings()
    return (
        settings.listening_native_preview
        and settings.app_env in {"dev", "test"}
        and settings.deployment_profile == "local"
    )


def require_native() -> None:
    if not get_settings().listening_native_enabled:
        raise HTTPException(404, "Prática nativa indisponível.")


def visible(content: NativeContent) -> bool:
    return content.status == "published" or (content.status == "draft" and preview_allowed())


def activity(content: NativeContent) -> NativeActivityOut:
    # Whitelist deliberada: transcript, answer_ids e explanation nunca entram aqui.
    return NativeActivityOut(
        slug=content.slug,
        version=content.version,
        title=content.title,
        topic=content.topic,
        level=content.level,
        preview=content.status == "draft",
        instructions=content.instructions,
        questions=[
            NativeQuestion(**q.model_dump(exclude={"answer_ids", "explanation"}))
            for q in content.questions
        ],
        map_rows=content.map_rows,
        map_description=content.map_description,
        audio_duration_seconds=content.audio_duration_seconds,
        attribution=content.attribution,
        rights_note=content.rights_note,
    )


async def version_for(
    session: Session, slug: str, version: int | None = None
) -> NativeListeningVersion:
    require_native()
    query = select(NativeListeningVersion).where(NativeListeningVersion.slug == slug)
    if version is not None:
        query = query.where(NativeListeningVersion.version == version)
    for row in await session.scalars(query.order_by(NativeListeningVersion.version.desc())):
        if visible(NativeContent.model_validate(row.content)):
            return row
    raise HTTPException(404, "Atividade ou versão indisponível.")


async def owner_lock(session: Session, user_id: int) -> None:
    if await session.scalar(select(User.id).where(User.id == user_id).with_for_update()) is None:
        raise HTTPException(401, "Conta inexistente.")


async def owned(session: Session, session_id: int, user_id: int) -> NativeListeningSession:
    require_native()
    row = await session.scalar(
        select(NativeListeningSession).where(
            NativeListeningSession.id == session_id,
            NativeListeningSession.user_id == user_id,
        )
    )
    if row is None:
        raise HTTPException(404, "Sessão não encontrada.")
    return row


async def output(session: Session, row: NativeListeningSession) -> NativeSessionOut:
    version = await session.get(NativeListeningVersion, row.version_id)
    assert version is not None
    content = NativeContent.model_validate(version.content)
    if not visible(content):
        raise HTTPException(404, "Atividade indisponível; seu histórico está em Meus dados.")
    events = list(
        await session.scalars(
            select(NativeListeningResponse)
            .where(
                NativeListeningResponse.session_id == row.id,
                NativeListeningResponse.user_id == row.user_id,
            )
            .order_by(NativeListeningResponse.revision)
        )
    )
    questions = {q.id: q for q in content.questions}
    seen: set[str] = set()
    feedback = []
    score, support = 0, False
    for event in events:
        payload = event.payload
        if payload["kind"] == "transcript":
            support = True
            continue
        question = questions[payload["question_id"]]
        first = question.id not in seen
        correct = payload["kind"] == "answer" and set(payload["selected_ids"]) == set(
            question.answer_ids
        )
        score += int(first and correct)
        seen.add(question.id)
        feedback.append(
            NativeFeedbackOut(
                question_id=question.id,
                kind=payload["kind"],
                selected_ids=payload["selected_ids"],
                correct=correct,
                first_response=first,
                answer_ids=question.answer_ids,
                explanation=question.explanation,
            )
        )
    return NativeSessionOut(
        id=row.id,
        activity=activity(content),
        revision=row.revision,
        completed=len(seen) == len(questions),
        score=score,
        total=len(questions),
        support_revealed=support,
        transcript=content.transcript if support else None,
        feedback=feedback,
        created_at=row.created_at,
    )


@router.get("/native", response_model=list[NativeActivityOut])
async def catalog(user: UsuarioAtual, session: Session) -> list[NativeActivityOut]:
    require_native()
    items: dict[str, NativeActivityOut] = {}
    for row in await session.scalars(
        select(NativeListeningVersion).order_by(
            NativeListeningVersion.slug,
            NativeListeningVersion.version.desc(),
        )
    ):
        content = NativeContent.model_validate(row.content)
        if row.slug not in items and visible(content):
            items[row.slug] = activity(content)
    return list(items.values())


@router.get("/native/{slug}", response_model=NativeActivityOut)
async def detail(slug: str, user: UsuarioAtual, session: Session) -> NativeActivityOut:
    return activity(NativeContent.model_validate((await version_for(session, slug)).content))


@router.get(
    "/native/{slug}/versions/{version}/audio",
    response_class=FileResponse,
    responses={
        200: {"content": {"audio/mpeg": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
async def audio(slug: str, version: int, user: UsuarioAtual, session: Session) -> FileResponse:
    content = NativeContent.model_validate((await version_for(session, slug, version)).content)
    try:
        path = media_path(content)
    except (ValueError, OSError):
        raise HTTPException(503, "Áudio indisponível. Tente novamente mais tarde.") from None
    return FileResponse(
        path, media_type="audio/mpeg", headers={"Cache-Control": "private, no-store"}
    )


@router.post("/native/{slug}/sessions", response_model=NativeSessionOut)
async def start(
    slug: str, body: NativeStartIn, user: UsuarioAtual, session: Session
) -> NativeSessionOut:
    require_native()
    await owner_lock(session, user.id)
    row = await session.scalar(
        select(NativeListeningSession).where(
            NativeListeningSession.user_id == user.id,
            NativeListeningSession.operation_key == str(body.operation_key),
        )
    )
    version = await version_for(session, slug, body.version)
    if row is not None and row.version_id != version.id:
        raise HTTPException(409, "Chave de início já usada com outra atividade ou versão.")
    if row is None:
        row = NativeListeningSession(
            user_id=user.id,
            version_id=version.id,
            operation_key=str(body.operation_key),
            revision=0,
        )
        session.add(row)
        await session.flush()
    result = await output(session, row)
    await session.commit()
    return result


@router.get("/sessions/{session_id}", response_model=NativeSessionOut)
async def get_native_session(
    session_id: int, user: UsuarioAtual, session: Session
) -> NativeSessionOut:
    return await output(session, await owned(session, session_id, user.id))


@router.post("/sessions/{session_id}/responses", response_model=NativeSessionOut)
async def respond(
    session_id: int,
    body: NativeResponseIn,
    user: UsuarioAtual,
    session: Session,
) -> NativeSessionOut:
    require_native()
    await owner_lock(session, user.id)
    row = await owned(session, session_id, user.id)
    current = await output(session, row)
    payload = {
        "kind": body.kind,
        "question_id": body.question_id,
        "selected_ids": sorted(body.selected_ids),
    }
    receipt = await session.scalar(
        select(NativeListeningResponse).where(
            NativeListeningResponse.user_id == user.id,
            NativeListeningResponse.operation_key == str(body.operation_key),
        )
    )
    if receipt is not None:
        if (receipt.session_id, receipt.expected_revision, receipt.payload) != (
            row.id,
            body.expected_revision,
            payload,
        ):
            raise HTTPException(409, "Chave já usada com outra resposta.")
        return current
    if row.revision != body.expected_revision:
        raise HTTPException(409, "A sessão mudou. Atualize antes de responder novamente.")
    if row.revision >= 100:
        raise HTTPException(409, "Limite de tentativas desta sessão atingido.")
    if body.kind != "transcript":
        question = next((q for q in current.activity.questions if q.id == body.question_id), None)
        if question is None:
            raise HTTPException(422, "Questão desconhecida.")
        if body.kind == "answer" and (
            len(body.selected_ids) != question.selection_count
            or not set(body.selected_ids) <= {option.id for option in question.options}
        ):
            raise HTTPException(422, "Selecione a quantidade solicitada de opções válidas.")
    row.revision += 1
    session.add(
        NativeListeningResponse(
            user_id=user.id,
            session_id=row.id,
            operation_key=str(body.operation_key),
            expected_revision=body.expected_revision,
            revision=row.revision,
            payload=payload,
        )
    )
    await session.flush()
    result = await output(session, row)
    await session.commit()
    return result
