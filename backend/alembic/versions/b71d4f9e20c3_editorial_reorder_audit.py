"""40B.2g: append-only receipts for controlled editorial reordering."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b71d4f9e20c3"
down_revision = "a06f2ce1487b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editorial_reorder_event",
        sa.Column("operation_key", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("operator_label", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column(
            "db_actor", sa.String(128), server_default=sa.text("current_user"), nullable=False
        ),
        sa.Column(
            "db_login", sa.String(128), server_default=sa.text("session_user"), nullable=False
        ),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("catalog_before_sha256", sa.String(64), nullable=False),
        sa.Column("catalog_candidate_sha256", sa.String(64), nullable=False),
        sa.Column("catalog_after_sha256", sa.String(64), nullable=False),
        sa.Column("changes", postgresql.JSONB(), nullable=False),
        sa.Column("impact", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "reason_code IN ('pedagogical_sequence', 'accessibility_sequence', "
            "'curriculum_reorganization')",
            name="ck_reorder_reason",
        ),
        sa.CheckConstraint("plan_sha256 ~ '^[0-9a-f]{64}$'", name="ck_reorder_plan_hash"),
        sa.CheckConstraint(
            "catalog_before_sha256 ~ '^[0-9a-f]{64}$'", name="ck_reorder_before_hash"
        ),
        sa.CheckConstraint(
            "catalog_candidate_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_reorder_candidate_hash",
        ),
        sa.CheckConstraint(
            "catalog_after_sha256 ~ '^[0-9a-f]{64}$'", name="ck_reorder_after_hash"
        ),
    )
    schema = op.get_bind().dialect.identifier_preparer.quote_schema(
        op.get_bind().scalar(sa.text("SELECT current_schema()"))
    )
    op.execute(f"""CREATE FUNCTION {schema}.aulas_keep_reorder_event() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, {schema} AS $$
      BEGIN
        RAISE EXCEPTION 'reorder receipt is immutable' USING ERRCODE = '23514';
      END $$""")
    op.execute(f"REVOKE ALL ON FUNCTION {schema}.aulas_keep_reorder_event() FROM PUBLIC")
    op.execute(f"""CREATE TRIGGER editorial_reorder_event_immutable
      BEFORE UPDATE OR DELETE ON {schema}.editorial_reorder_event
      FOR EACH ROW EXECUTE FUNCTION {schema}.aulas_keep_reorder_event()""")
    op.execute(f"""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aulas_runtime') THEN
        REVOKE ALL ON {schema}.editorial_reorder_event FROM aulas_runtime;
      END IF;
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aulas_worker') THEN
        REVOKE ALL ON {schema}.editorial_reorder_event FROM aulas_worker;
      END IF;
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aulas_backup') THEN
        GRANT SELECT ON {schema}.editorial_reorder_event TO aulas_backup;
      END IF;
    END $$""")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM editorial_reorder_event)")):
        raise RuntimeError("Preserve reorder audit: downgrade requires an empty receipt table.")
    op.drop_table("editorial_reorder_event")
    op.execute("DROP FUNCTION aulas_keep_reorder_event()")
