"""Deck de revisão espaçada."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.models import Lesson, ReviewCard, User, VocabItem
from app.db.session import get_session
from app.domain.sm2 import Estado, revisar
from app.schemas.review import CardOut, DeckSummaryOut, GradeIn, GradeOut

router = APIRouter(prefix="/review", tags=["review"])


async def adicionar_cartas(session: AsyncSession, usuario: User, itens: list[VocabItem]) -> int:
    """Cria cartas que ainda não existem. Devolve quantas foram criadas.

    Idempotente: um item que já está no deck é ignorado, e não tem o
    agendamento reiniciado — isso apagaria o histórico de quem já estuda.
    Carta nova nasce vencida, para entrar na revisão de hoje.
    """
    if not itens:
        return 0
    ja_tem = {
        c.vocab_item_id
        for c in (
            await session.execute(
                select(ReviewCard).where(
                    ReviewCard.user_id == usuario.id,
                    ReviewCard.vocab_item_id.in_([i.id for i in itens]),
                )
            )
        ).scalars()
    }
    agora = datetime.now(UTC)
    novas = 0
    for item in itens:
        if item.id in ja_tem:
            continue
        session.add(ReviewCard(user_id=usuario.id, vocab_item_id=item.id, due_at=agora))
        novas += 1
    await session.flush()
    return novas


async def _resumo(session: AsyncSession, usuario: User, criadas: int = 0) -> DeckSummaryOut:
    total = (
        await session.execute(
            select(func.count()).select_from(ReviewCard).where(ReviewCard.user_id == usuario.id)
        )
    ).scalar_one()
    vencidas = (
        await session.execute(
            select(func.count())
            .select_from(ReviewCard)
            .where(ReviewCard.user_id == usuario.id, ReviewCard.due_at <= datetime.now(UTC))
        )
    ).scalar_one()
    return DeckSummaryOut(due_now=vencidas, total_cards=total, added=criadas)


@router.get("/summary", response_model=DeckSummaryOut)
async def resumo(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeckSummaryOut:
    return await _resumo(session, usuario)


@router.get("/due", response_model=list[CardOut])
async def vencidas(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[CardOut]:
    """Cartas do usuário logado cujo prazo já chegou, da mais atrasada primeiro."""
    linhas = (
        await session.execute(
            select(ReviewCard, VocabItem, Lesson.number)
            .join(VocabItem, ReviewCard.vocab_item_id == VocabItem.id)
            .join(Lesson, VocabItem.lesson_id == Lesson.id)
            .where(ReviewCard.user_id == usuario.id, ReviewCard.due_at <= datetime.now(UTC))
            .order_by(ReviewCard.due_at)
            .limit(limit)
        )
    ).all()
    return [
        CardOut(
            id=carta.id,
            vocab_item_id=item.id,
            term=item.term,
            ipa=item.ipa,
            translation_pt=item.translation_pt,
            example_en=item.example_en,
            lesson_number=numero,
            ease_factor=carta.ease_factor,
            interval_days=carta.interval_days,
            repetitions=carta.repetitions,
            lapses=carta.lapses,
            due_at=carta.due_at,
        )
        for carta, item, numero in linhas
    ]


@router.post("/{card_id}/grade", response_model=GradeOut)
async def avaliar(
    card_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[GradeIn, Body()],
) -> GradeOut:
    """Aplica o SM-2 à carta e reagenda."""
    carta = (
        await session.execute(
            select(ReviewCard).where(ReviewCard.id == card_id, ReviewCard.user_id == usuario.id)
        )
    ).scalar_one_or_none()
    # 404 e não 403 para carta de outra pessoa: dizer "existe, mas não é sua"
    # já conta quantas cartas os outros têm.
    if carta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Carta {card_id} não existe."
        )

    agora = datetime.now(UTC)
    novo, proxima = revisar(
        Estado(
            ease_factor=carta.ease_factor,
            interval_days=carta.interval_days,
            repetitions=carta.repetitions,
            lapses=carta.lapses,
        ),
        corpo.quality,
        agora,
    )
    carta.ease_factor = novo.ease_factor
    carta.interval_days = novo.interval_days
    carta.repetitions = novo.repetitions
    carta.lapses = novo.lapses
    carta.due_at = proxima
    carta.last_reviewed_at = agora
    await session.commit()

    return GradeOut(
        id=carta.id,
        interval_days=carta.interval_days,
        ease_factor=carta.ease_factor,
        repetitions=carta.repetitions,
        lapses=carta.lapses,
        due_at=carta.due_at,
    )


@router.post("/items/{vocab_item_id}", response_model=DeckSummaryOut)
async def adicionar_item(
    vocab_item_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeckSummaryOut:
    """Põe um item de vocabulário no deck."""
    item = (
        await session.execute(select(VocabItem).where(VocabItem.id == vocab_item_id))
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Item {vocab_item_id} não existe."
        )
    criadas = await adicionar_cartas(session, usuario, [item])
    await session.commit()
    return await _resumo(session, usuario, criadas)


@router.post("/lessons/{number}", response_model=DeckSummaryOut)
async def adicionar_aula(
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeckSummaryOut:
    """Põe todo o vocabulário de uma aula no deck."""
    aula = (
        await session.execute(select(Lesson).where(Lesson.number == number))
    ).scalar_one_or_none()
    if aula is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Aula {number} não existe."
        )
    criadas = await adicionar_cartas(session, usuario, list(aula.vocab))
    await session.commit()
    return await _resumo(session, usuario, criadas)
