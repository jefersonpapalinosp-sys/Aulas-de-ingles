"""Contrato do índice promovido após o benchmark sintético da Sprint 41."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_notebook_keyset_index_is_valid_and_matches_cursor(
    session: AsyncSession,
) -> None:
    row = (
        await session.execute(
            text(
                "SELECT i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid) AS definition "
                "FROM pg_index i "
                "JOIN pg_class idx ON idx.oid=i.indexrelid "
                "JOIN pg_class tbl ON tbl.oid=i.indrelid "
                "WHERE tbl.relname='notebook_entry' "
                "AND idx.relname='ix_notebook_entry_user_updated_id'"
            )
        )
    ).one()

    assert row.indisvalid is True
    assert row.indisready is True
    assert row.definition.endswith("USING btree (user_id, updated_at, id)")
