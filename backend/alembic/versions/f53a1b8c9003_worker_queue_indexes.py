"""Sprint 53: índices medidos para claim e recuperação da fila."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f53a1b8c9003"
down_revision: str | None = "e52a1b8c9002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = (
    ("ix_transcription_job_kind_status", ["kind", "status", "next_attempt_at"], None),
    ("ix_transcription_job_status", ["status"], None),
    ("ix_transcription_job_next_attempt_at", ["next_attempt_at"], None),
)
NEW = (
    ("ix_transcription_job_queued", ["status", "next_attempt_at", "id"], "status = 'queued'"),
    ("ix_transcription_job_processing", ["processing_started_at", "id"], "status = 'processing'"),
)


def _exists(name: str, table: str, columns: list[str], predicate: str | None) -> bool:
    row = (
        op.get_bind()
        .execute(
            sa.text("""
        SELECT i.indisvalid, i.indisready, i.indisunique, t.relname,
               ARRAY(SELECT a.attname::text FROM unnest(i.indkey) WITH ORDINALITY k(n, pos)
                     JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.n ORDER BY k.pos),
               pg_get_expr(i.indpred, i.indrelid)
        FROM pg_index i JOIN pg_class idx ON idx.oid=i.indexrelid
        JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace ns ON ns.oid=idx.relnamespace
        WHERE ns.nspname='public' AND idx.relname=:name
    """),
            {"name": name},
        )
        .one_or_none()
    )
    if row is None:
        return False

    # pg_get_expr insere parênteses e explicita cast de varchar na comparação.
    def normalized(value: str | None) -> str:
        return (value or "").replace("(", "").replace(")", "").replace("::text", "")

    if (
        not row[0]
        or not row[1]
        or row[2]
        or row[3] != table
        or row[4] != columns
        or normalized(row[5]) != normalized(predicate)
    ):
        raise RuntimeError(f"Índice {name} inválido ou divergente; inspecione antes de repetir.")
    return True


def _replace(create, remove) -> None:
    table = "transcription_job"
    # Verifica todos antes de DDL. Repetição aceita etapas já concluídas.
    for name, columns, predicate in (*create, *remove):
        _exists(name, table, columns, predicate)
    for name, columns, predicate in create:
        if not _exists(name, table, columns, predicate):
            with op.get_context().autocommit_block():
                op.create_index(
                    name,
                    table,
                    columns,
                    postgresql_concurrently=True,
                    postgresql_where=sa.text(predicate) if predicate else None,
                )
        if not _exists(name, table, columns, predicate):
            raise RuntimeError(f"Índice {name} não foi criado.")
    for name, columns, predicate in remove:
        if _exists(name, table, columns, predicate):
            with op.get_context().autocommit_block():
                op.drop_index(name, table_name=table, postgresql_concurrently=True)


def upgrade() -> None:
    _replace(NEW, OLD)


def downgrade() -> None:
    _replace(OLD, NEW)
