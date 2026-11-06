"""Sprint 52: índices concorrentes para exclusão e retenção."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e52a1b8c9002"
down_revision: str | None = "d52a1b8c9001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = (
    ("ix_study_active_interval_event_id", "study_active_interval", ["event_id"], None),
    ("ix_review_event_item_id", "review_event", ["item_id"], None),
    ("ix_practice_session_source_session_id", "practice_session", ["source_session_id"], None),
    (
        "ix_dialogue_turn_retention",
        "dialogue_turn",
        ["expires_at", "id"],
        "transcript IS NOT NULL OR partner_text IS NOT NULL OR hints <> '[]'::jsonb",
    ),
    ("ix_speaking_dialogue_audio", "speaking_attempt", ["id"], "origin = 'dialogue'"),
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


def upgrade() -> None:
    for name, table, columns, predicate in INDEXES:
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
            raise RuntimeError(f"Índice {name} ausente após criação.")


def downgrade() -> None:
    for name, table, columns, predicate in reversed(INDEXES):
        if _exists(name, table, columns, predicate):
            with op.get_context().autocommit_block():
                op.drop_index(name, table_name=table, postgresql_concurrently=True)
