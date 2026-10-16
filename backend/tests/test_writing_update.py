"""O atalho legado de rubricas deve falhar antes de tocar no banco."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.writing_update import update_writing_rubrics


async def test_update_direta_foi_desativada_sem_abrir_transacao(
    session: AsyncSession,
) -> None:
    assert not session.in_transaction()
    with pytest.raises(ValueError, match="Atualização direta"):
        await update_writing_rubrics(session)
    assert not session.in_transaction()
