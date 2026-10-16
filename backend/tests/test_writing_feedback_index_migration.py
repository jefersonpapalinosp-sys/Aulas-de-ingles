"""Contrato do indice promovido apos o benchmark sintetico da Sprint 41."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_writing_feedback_keyset_index_matches_cursor(
    session: AsyncSession,
) -> None:
    row = (
        await session.execute(
            text(
                "SELECT i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid) AS definition "
                "FROM pg_index i "
                "JOIN pg_class idx ON idx.oid=i.indexrelid "
                "JOIN pg_class tbl ON tbl.oid=i.indrelid "
                "WHERE tbl.relname='writing_feedback' "
                "AND idx.relname='ix_writing_feedback_user_prompt_created_id'"
            )
        )
    ).one()

    assert row.indisvalid is True
    assert row.indisready is True
    assert row.definition.endswith("USING btree (user_id, prompt_id, created_at, id)")
