"""índice medido para paginação keyset do caderno

Revision ID: c82f4a9d117e
Revises: b71d4f9e20c3
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c82f4a9d117e"
down_revision: str | None = "b71d4f9e20c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_notebook_entry_user_updated_id"
EXPECTED_SUFFIX = "USING btree (user_id, updated_at, id)"


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
                "WHERE ns.nspname=current_schema() AND tbl.relname='notebook_entry' "
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
            f"Índice {INDEX} existe, mas está inválido, incompleto ou divergente. "
            "Inspecione pg_index/pg_get_indexdef e remova somente esse índice com "
            "DROP INDEX CONCURRENTLY antes de repetir a migration."
        )


def upgrade() -> None:
    existing = _state()
    if existing is not None:
        _require_expected(existing)
        return
    # CONCURRENTLY não pode ficar na transação Alembic. Se a criação for interrompida,
    # o preflight acima recusa o artefato inválido em vez de apagá-lo silenciosamente.
    with op.get_context().autocommit_block():
        op.create_index(
            INDEX,
            "notebook_entry",
            ["user_id", "updated_at", "id"],
            unique=False,
            postgresql_concurrently=True,
        )
    created = _state()
    if created is None:
        raise RuntimeError(f"Índice {INDEX} não foi criado.")
    _require_expected(created)


def downgrade() -> None:
    existing = _state()
    if existing is None:
        return
    _require_expected(existing)
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name="notebook_entry", postgresql_concurrently=True)
