"""Contrato do indice promovido apos o benchmark sintetico da Sprint 41."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_review_keyset_index_is_valid_and_matches_cursor(
    session: AsyncSession,
) -> None:
    row = (
        await session.execute(
            text(
                "SELECT i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid) AS definition "
                "FROM pg_index i "
                "JOIN pg_class idx ON idx.oid=i.indexrelid "
                "JOIN pg_class tbl ON tbl.oid=i.indrelid "
                "WHERE tbl.relname='review_item' "
                "AND idx.relname='ix_review_item_user_status_created_id'"
            )
        )
    ).one()

    assert row.indisvalid is True
    assert row.indisready is True
    assert row.definition.endswith("USING btree (user_id, status, created_at, id)")
