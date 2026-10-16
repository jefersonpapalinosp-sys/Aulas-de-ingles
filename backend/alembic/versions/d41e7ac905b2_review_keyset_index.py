"""indice medido para paginacao keyset da revisao

Revision ID: d41e7ac905b2
Revises: c82f4a9d117e
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d41e7ac905b2"
down_revision: str | None = "c82f4a9d117e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_review_item_user_status_created_id"
EXPECTED_SUFFIX = "USING btree (user_id, status, created_at, id)"


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
                "WHERE ns.nspname=current_schema() AND tbl.relname='review_item' "
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
    # CONCURRENTLY nao pode ficar na transacao Alembic. Se a criacao for interrompida,
    # o preflight recusa o artefato invalido em vez de apaga-lo silenciosamente.
    with op.get_context().autocommit_block():
        op.create_index(
            INDEX,
            "review_item",
            ["user_id", "status", "created_at", "id"],
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
        op.drop_index(INDEX, table_name="review_item", postgresql_concurrently=True)
