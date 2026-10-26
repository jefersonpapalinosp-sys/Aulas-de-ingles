"""Origens da fila de revisão, compartilhadas pelos routers que as alimentam.

Quatro routers (`me`, `progress`, `writing`, `speaking`) criam e removem itens
de revisão; o módulo existe para que nenhum deles precise importar outro router.
Uma origem (`source_key`) vale uma vez: reenvio atualiza o conteúdo e soma
revisão, nunca duplica a carta.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReviewItem, User, VocabItem
from app.schemas.review import ReviewItemType


async def adicionar_item_revisao(
    session: AsyncSession,
    usuario: User,
    *,
    lesson_id: int,
    item_type: ReviewItemType,
    source_type: str,
    source_id: int,
    source_key: str,
    skill: str,
    prompt: str,
    answer: str,
    origin_reason: str,
    estimated_seconds: int,
    prompt_note: str | None = None,
    context: str | None = None,
    vocab_item_id: int | None = None,
    media_url: str | None = None,
    cue_start_seconds: float | None = None,
    cue_end_seconds: float | None = None,
) -> bool:
    """Cria uma origem uma vez; novos erros atualizam o conteúdo sem duplicar."""
    values = dict(
        user_id=usuario.id,
        lesson_id=lesson_id,
        vocab_item_id=vocab_item_id,
        item_type=item_type,
        source_type=source_type,
        source_id=source_id,
        source_key=source_key,
        skill=skill,
        prompt=prompt,
        prompt_note=prompt_note,
        answer=answer,
        context=context,
        origin_reason=origin_reason,
        media_url=media_url,
        cue_start_seconds=cue_start_seconds,
        cue_end_seconds=cue_end_seconds,
        estimated_seconds=estimated_seconds,
        due_at=datetime.now(UTC),
    )
    created = (
        await session.execute(
            insert(ReviewItem)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_review_item_user_source")
            .returning(ReviewItem.id)
        )
    ).scalar_one_or_none()
    if created is not None:
        return True
    item = (
        await session.execute(
            select(ReviewItem)
            .where(
                ReviewItem.user_id == usuario.id,
                ReviewItem.source_key == source_key,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if item is not None:
        content_fields = (
            "prompt",
            "prompt_note",
            "answer",
            "context",
            "origin_reason",
            "media_url",
            "cue_start_seconds",
            "cue_end_seconds",
        )
        if any(getattr(item, field) != values[field] for field in content_fields):
            item.revision += 1
        item.prompt = prompt
        item.prompt_note = prompt_note
        item.answer = answer
        item.context = context
        item.origin_reason = origin_reason
        item.media_url = media_url
        item.cue_start_seconds = cue_start_seconds
        item.cue_end_seconds = cue_end_seconds
        return False

    return False


async def remover_item_por_origem(session: AsyncSession, user_id: int, source_key: str) -> None:
    item = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.user_id == user_id,
                ReviewItem.source_key == source_key,
            )
        )
    ).scalar_one_or_none()
    if item is not None:
        await session.delete(item)


async def adicionar_cartas(session: AsyncSession, usuario: User, itens: list[VocabItem]) -> int:
    """Compatibilidade do deck: vocabulário agora entra na fila generalizada."""
    novas = 0
    for item in sorted(itens, key=lambda value: value.id):
        novas += int(
            await adicionar_item_revisao(
                session,
                usuario,
                lesson_id=item.lesson_id,
                item_type="vocabulary",
                source_type="vocab_item",
                source_id=item.id,
                source_key=f"vocab:{item.id}",
                skill="vocabulary",
                prompt=item.term,
                prompt_note=item.ipa,
                answer=item.translation_pt,
                context=item.example_en,
                origin_reason="Vocabulário incluído no seu deck de estudo.",
                estimated_seconds=45,
                vocab_item_id=item.id,
            )
        )
    return novas
