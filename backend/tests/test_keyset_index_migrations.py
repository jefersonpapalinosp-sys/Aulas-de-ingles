"""Contratos dos índices promovidos por benchmark (Sprint 41) e pelo rate limit (DB-44).

Um caso por índice: o teste falha se a migration não o criou, se ele ficou
inválido ou se as colunas deixaram de casar com a ordenação do cursor/filtro.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

INDEXES = [
    ("notebook_entry", "ix_notebook_entry_user_updated_id", "(user_id, updated_at, id)"),
    ("review_item", "ix_review_item_user_status_created_id", "(user_id, status, created_at, id)"),
    (
        "writing_feedback",
        "ix_writing_feedback_user_prompt_created_id",
        "(user_id, prompt_id, created_at, id)",
    ),
    ("auth_rate_bucket", "ix_auth_rate_bucket_window_start", "(window_start)"),
]


@pytest.mark.parametrize(("table", "index", "columns"), INDEXES, ids=[i[1] for i in INDEXES])
async def test_promoted_index_is_valid_and_matches_access_path(
    session: AsyncSession, table: str, index: str, columns: str
) -> None:
    row = (
        await session.execute(
            text(
                "SELECT i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid) AS definition "
                "FROM pg_index i "
                "JOIN pg_class idx ON idx.oid=i.indexrelid "
                "JOIN pg_class tbl ON tbl.oid=i.indrelid "
                "WHERE tbl.relname=:table AND idx.relname=:index"
            ),
            {"table": table, "index": index},
        )
    ).one()

    assert row.indisvalid is True
    assert row.indisready is True
    assert row.definition.endswith(f"USING btree {columns}")
