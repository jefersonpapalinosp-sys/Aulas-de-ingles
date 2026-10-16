"""indice medido para paginacao keyset do feedback de escrita

Revision ID: e41f6c2a8d90
Revises: d41e7ac905b2
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e41f6c2a8d90"
down_revision: str | None = "d41e7ac905b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_writing_feedback_user_prompt_created_id"
EXPECTED_SUFFIX = "USING btree (user_id, prompt_id, created_at, id)"


def _state() -> tuple[bool, bool, str] | None:
    row = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT i.indisvalid,i.indisready,pg_get_indexdef(i.indexrelid) "
                "FROM pg_index i "
                "JOIN pg_class idx ON idx.oid=i.indexrelid "
                "JOIN pg_class tbl ON tbl.oid=i.indrelid "
                "JOIN pg_namespace ns ON ns.oid=tbl.relnamespace "
                "WHERE ns.nspname=current_schema() AND tbl.relname='writing_feedback' "
                "AND idx.relname=:name"
            ),
            {"name": INDEX},
        )
        .one_or_none()
    )
    if row is None:
        return None
    return bool(row.indisvalid), bool(row.indisready), str(row.pg_get_indexdef)


def _require_expected(state: tuple[bool, bool, str]) -> None:
    valid, ready, definition = state
    if not valid or not ready or not definition.endswith(EXPECTED_SUFFIX):
        raise RuntimeError(
            f"Indice {INDEX} existe, mas esta invalido, incompleto ou divergente. "
            "Inspecione pg_index/pg_get_indexdef e remova somente esse indice com "
            "DROP INDEX CONCURRENTLY antes de repetir a migration."
        )


def upgrade() -> None:
    existing = _state()
    if existing is not None:
        _require_expected(existing)
        return
    with op.get_context().autocommit_block():
        op.create_index(
            INDEX,
            "writing_feedback",
            ["user_id", "prompt_id", "created_at", "id"],
            unique=False,
            postgresql_concurrently=True,
        )
    created = _state()
    if created is None:
        raise RuntimeError(f"Indice {INDEX} nao foi criado.")
    _require_expected(created)


def downgrade() -> None:
    existing = _state()
    if existing is None:
        return
    _require_expected(existing)
    with op.get_context().autocommit_block():
        op.drop_index(
            INDEX,
            table_name="writing_feedback",
            postgresql_concurrently=True,
        )
