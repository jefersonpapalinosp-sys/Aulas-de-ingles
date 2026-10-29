"""Admissão atômica por usuário; nunca manter o lock durante o provedor."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import AssistReservation, User

# As modalidades do assistente **não compartilham teto**. Uma conversa de 12
# turnos esgotaria num gesto a cota de 5 análises de escrita do dia, e o aluno
# perderia a escrita por ter conversado. São dois orçamentos: `daily_limit` diz
# qual é o de cada modalidade e `_group` diz quem conta junto com quem.
DIALOGUE_MODALITY = "conversation"
LEGACY_MODALITIES = ("writing", "transcription")


def daily_limit(modality: str) -> int:
    settings = get_settings()
    if modality == DIALOGUE_MODALITY:
        return settings.assist_dialogue_daily_turns
    return settings.assist_daily_quota


def _group(modality: str) -> tuple[str, ...]:
    """Modalidades que dividem o mesmo teto diário."""
    if modality == DIALOGUE_MODALITY:
        return (DIALOGUE_MODALITY,)
    return LEGACY_MODALITIES


class QuotaExceeded(Exception):
    pass


@dataclass(frozen=True)
class Usage:
    reserved: int
    consumed: int
    cost: int
    incomplete: bool
    resets_at: datetime

    @property
    def used(self) -> int:
        return self.reserved + self.consumed


async def usage(
    session: AsyncSession,
    user_id: int,
    now: datetime | None = None,
    *,
    modalities: Sequence[str] | None = None,
) -> Usage:
    """Consumo do dia. Sem `modalities`, soma todas — útil para manutenção e
    relatório; um teto sempre pergunta pelo seu próprio grupo."""
    now = now or datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reserved = (AssistReservation.state == "reserved") & (AssistReservation.expires_at > now)
    consumed = AssistReservation.state == "consumed"
    row = (
        await session.execute(
            select(
                func.count().filter(reserved),
                func.count().filter(consumed),
                func.coalesce(func.sum(AssistReservation.cost_microusd).filter(consumed), 0),
                func.count().filter(consumed & ~AssistReservation.cost_known),
            ).where(
                AssistReservation.user_id == user_id,
                AssistReservation.created_at >= start,
                AssistReservation.created_at < start + timedelta(days=1),
                *(
                    [AssistReservation.modality.in_(tuple(modalities))]
                    if modalities is not None
                    else []
                ),
            )
        )
    ).one()
    return Usage(int(row[0]), int(row[1]), int(row[2]), bool(row[3]), start + timedelta(days=1))


async def lock_user(session: AsyncSession, user_id: int) -> None:
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())


async def reserve(
    session: AsyncSession, user_id: int, key: str, fingerprint: str, modality: str
) -> tuple[AssistReservation, bool]:
    await lock_user(session, user_id)
    now = datetime.now(UTC)
    existing = (
        await session.execute(
            select(AssistReservation).where(
                AssistReservation.user_id == user_id,
                AssistReservation.request_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.fingerprint != fingerprint or existing.modality != modality:
            raise HTTPException(409, "Chave de análise já utilizada com outro conteúdo.")
        return existing, False
    # Aguarda despachos concorrentes antes de descontar reservas vencidas.
    # Sem este lock, MVCC poderia mostrar uma reserva já vencida enquanto um
    # worker ainda confirma consumed, admitindo uma unidade extra nesse intervalo.
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    grupo = _group(modality)
    await session.execute(
        select(AssistReservation.id)
        .where(
            AssistReservation.user_id == user_id,
            AssistReservation.state == "reserved",
            AssistReservation.created_at >= start,
            AssistReservation.created_at < start + timedelta(days=1),
            AssistReservation.modality.in_(grupo),
        )
        .order_by(AssistReservation.id)
        .with_for_update()
    )
    if (await usage(session, user_id, now, modalities=grupo)).used >= daily_limit(modality):
        raise QuotaExceeded
    reservation = AssistReservation(
        user_id=user_id,
        request_key=key,
        fingerprint=fingerprint,
        modality=modality,
        provider_key=f"assist-{uuid4().hex}",
        state="reserved",
        created_at=now,
        expires_at=now + timedelta(seconds=get_settings().assist_reservation_seconds),
    )
    session.add(reservation)
    await session.flush()
    return reservation, True


async def consume(session: AsyncSession, reservation_id: int | None) -> bool:
    """Idempotente para retries do mesmo job. Expiradas nunca chegam ao provedor."""
    if reservation_id is None:
        return False
    row = (
        await session.execute(
            select(AssistReservation)
            .where(AssistReservation.id == reservation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.state == "released":
        return False
    if row.state == "consumed":
        return True
    if row.expires_at <= datetime.now(UTC):
        row.state, row.reason = "released", "reservation_expired"
        return False
    row.state, row.dispatched_at = "consumed", datetime.now(UTC)
    return True


async def release(session: AsyncSession, reservation_id: int | None, reason: str) -> None:
    # Timeout ou exclusão depois do despacho NÃO devolvem a unidade.
    await session.execute(
        update(AssistReservation)
        .where(
            AssistReservation.id == reservation_id,
            AssistReservation.state == "reserved",
        )
        .values(state="released", reason=reason)
    )


async def record_cost(
    session: AsyncSession, reservation_id: int | None, cost: int, *, known: bool = True
) -> None:
    await session.execute(
        update(AssistReservation)
        .where(
            AssistReservation.id == reservation_id,
            AssistReservation.state == "consumed",
        )
        .values(cost_microusd=cost, cost_known=known)
    )
