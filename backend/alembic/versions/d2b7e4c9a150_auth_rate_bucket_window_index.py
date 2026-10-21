"""índice de janela para a limpeza do rate limit de autenticação (DB-44)

A limpeza `DELETE ... WHERE window_start < :corte` roda em todo login/registro.
`window_start` é a segunda coluna da PK, então o predicado não usava índice.

Revision ID: d2b7e4c9a150
Revises: a42c7d1e9f20
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2b7e4c9a150"
down_revision: str | None = "a42c7d1e9f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "auth_rate_bucket"
INDEX = "ix_auth_rate_bucket_window_start"
EXPECTED_SUFFIX = "USING btree (window_start)"


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
                "WHERE ns.nspname=current_schema() AND tbl.relname=:table "
                "AND idx.relname=:name"
            ),
            {"table": TABLE, "name": INDEX},
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
            TABLE,
            ["window_start"],
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
        op.drop_index(INDEX, table_name=TABLE, postgresql_concurrently=True)
