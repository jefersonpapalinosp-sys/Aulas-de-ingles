"""Sprint 59: catálogo externo independente e marcações autodeclaradas."""

import sqlalchemy as sa

from alembic import op

revision = "d59a1b8c9007"
down_revision = "c56b1c8d9006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listening_resource",
        sa.Column("slug", sa.String(100), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("topic", sa.String(50), nullable=False),
        sa.Column("level", sa.String(2), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_url", sa.String(400), nullable=False, unique=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("availability", sa.String(20), nullable=False),
        sa.Column("checked_on", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("level = 'A2' AND mode = 'external_link'", name="ck_listening_mode"),
        sa.CheckConstraint(
            "availability IN ('available', 'unavailable')", name="ck_listening_availability"
        ),
        sa.CheckConstraint("version > 0 AND position > 0", name="ck_listening_version"),
    )
    for table in ("listening_progress", "listening_operation"):
        columns = [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("app_user.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "resource_slug",
                sa.String(100),
                sa.ForeignKey("listening_resource.slug", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("state", sa.String(20), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        ]
        if table == "listening_operation":
            columns += [
                sa.Column("operation_key", sa.Uuid(as_uuid=False), nullable=False),
                sa.Column("expected_revision", sa.Integer(), nullable=False),
            ]
            unique = sa.UniqueConstraint("user_id", "operation_key")
            revision_check = "expected_revision >= 0 AND revision = expected_revision + 1"
        else:
            unique = sa.UniqueConstraint("user_id", "resource_slug")
            revision_check = "revision > 0"
        op.create_table(
            table,
            *columns,
            unique,
            sa.CheckConstraint(
                "state IN ('not_started', 'in_progress', 'completed')", name=f"ck_{table}_state"
            ),
            sa.CheckConstraint(revision_check, name=f"ck_{table}_revision"),
        )
        op.create_index(f"ix_{table}_resource_slug", table, ["resource_slug"])
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_runtime') THEN
        GRANT SELECT ON listening_resource, listening_progress, listening_operation TO aulas_runtime;
        GRANT INSERT, UPDATE ON listening_progress TO aulas_runtime;
        GRANT INSERT ON listening_operation TO aulas_runtime;
        GRANT USAGE ON SEQUENCE listening_progress_id_seq, listening_operation_id_seq TO aulas_runtime;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_backup') THEN
        GRANT SELECT ON listening_resource, listening_progress, listening_operation TO aulas_backup;
        GRANT SELECT ON SEQUENCE listening_progress_id_seq, listening_operation_id_seq TO aulas_backup;
      END IF;
    END $$;""")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM listening_progress) OR EXISTS (SELECT 1 FROM listening_operation) THEN
        RAISE EXCEPTION 'Listening contém dados pessoais; use rollback de aplicação, preservando o schema.';
      END IF;
    END $$;""")
    op.drop_table("listening_operation")
    op.drop_table("listening_progress")
    op.drop_table("listening_resource")
