"""Histórico privado por keyset, com o índice (user_id, started_at, id)."""

from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DialogueTurn, SpeakingDialogue
from app.pagination import TimeIdCursor, encode_time_id_cursor
from app.schemas.dialogue import DialoguePageOut, DialogueSummaryOut


def history_query(
    user_id: int, limit: int, cursor: TimeIdCursor | None = None
) -> Select[SpeakingDialogue, int]:
    count = (
        select(func.count(DialogueTurn.id))
        .where(
            DialogueTurn.dialogue_id == SpeakingDialogue.id,
            DialogueTurn.role == "student",
        )
        .correlate(SpeakingDialogue)
        .scalar_subquery()
    )
    query = select(SpeakingDialogue, count.label("used_turns")).where(
        SpeakingDialogue.user_id == user_id
    )
    if cursor is not None:
        query = query.where(
            tuple_(SpeakingDialogue.started_at, SpeakingDialogue.id)
            < tuple_(cursor.timestamp, cursor.row_id)
        )
    return query.order_by(SpeakingDialogue.started_at.desc(), SpeakingDialogue.id.desc()).limit(
        limit + 1
    )


async def history_page(
    session: AsyncSession, user_id: int, limit: int, cursor: TimeIdCursor | None = None
) -> DialoguePageOut:
    rows = (await session.execute(history_query(user_id, limit, cursor))).all()
    page = rows[:limit]
    return DialoguePageOut(
        items=[
            DialogueSummaryOut(
                id=d.id,
                lesson_id=d.lesson_id,
                mode=d.mode,
                state=d.state,
                partner_speaker=d.partner_speaker,
                turn_limit=d.turn_limit,
                turns_remaining=max(0, d.turn_limit - used),
                provider_name=d.provider_name,
                rubric_version=d.rubric_version,
                started_at=d.started_at,
                ended_at=d.ended_at,
            )
            for d, used in page
        ],
        next_cursor=(
            encode_time_id_cursor(page[-1][0].started_at, page[-1][0].id)
            if len(rows) > limit
            else None
        ),
    )
