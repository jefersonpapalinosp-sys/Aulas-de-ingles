"""40B.2b.3: append-only operational archive receipts; no catalog/data backfill."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d62a0ef357b9"
down_revision = "c51f9de246a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editorial_archive_event",
        sa.Column("operation_key", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "unit_id",
            sa.Integer(),
            sa.ForeignKey("course_unit.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("course_slug", sa.String(100), nullable=False),
        sa.Column("unit_slug", sa.String(100), nullable=False),
        sa.Column("operator_label", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column(
            "db_actor", sa.String(128), server_default=sa.text("current_user"), nullable=False
        ),
        sa.Column(
            "db_login", sa.String(128), server_default=sa.text("session_user"), nullable=False
        ),
        sa.Column("before_status", sa.String(20), nullable=False),
        sa.Column("after_status", sa.String(20), nullable=False),
        sa.Column("catalog_sha256", sa.String(64), nullable=False),
        sa.Column("impact", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "before_status = 'published' AND after_status = 'archived'",
            name="ck_archive_transition",
        ),
        sa.CheckConstraint(
            "reason_code IN ('editorial_review', 'source_unavailable', 'curriculum_reorganization')",
            name="ck_archive_reason",
        ),
        sa.CheckConstraint("catalog_sha256 ~ '^[0-9a-f]{64}$'", name="ck_archive_hash"),
    )
    schema = op.get_bind().dialect.identifier_preparer.quote_schema(
        op.get_bind().scalar(sa.text("SELECT current_schema()"))
    )
    op.execute(f"""CREATE FUNCTION {schema}.aulas_keep_archive_event() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, {schema} AS $$
      BEGIN
        RAISE EXCEPTION 'archive receipt is immutable' USING ERRCODE = '23514';
      END $$""")
    op.execute(f"REVOKE ALL ON FUNCTION {schema}.aulas_keep_archive_event() FROM PUBLIC")
    op.execute(f"""CREATE TRIGGER editorial_archive_event_immutable
      BEFORE UPDATE OR DELETE ON {schema}.editorial_archive_event
      FOR EACH ROW EXECUTE FUNCTION {schema}.aulas_keep_archive_event()""")
    op.execute(f"""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aulas_runtime') THEN
        REVOKE ALL ON {schema}.editorial_archive_event FROM aulas_runtime;
      END IF;
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aulas_worker') THEN
        REVOKE ALL ON {schema}.editorial_archive_event FROM aulas_worker;
      END IF;
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='aulas_backup') THEN
        GRANT SELECT ON {schema}.editorial_archive_event TO aulas_backup;
      END IF;
    END $$""")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM editorial_archive_event)")):
        raise RuntimeError("Preserve archive audit: downgrade requires an empty receipt table.")
    op.drop_table("editorial_archive_event")
    op.execute("DROP FUNCTION aulas_keep_archive_event()")
