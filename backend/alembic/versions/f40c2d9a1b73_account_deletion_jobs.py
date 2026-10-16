"""Sprint 40C: exclusao de conta e limpeza idempotente de arquivos

Revision ID: f40c2d9a1b73
Revises: e41f6c2a8d90
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f40c2d9a1b73"
down_revision: str | None = "e41f6c2a8d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_deletion_job",
        sa.Column("operation_key", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(50)),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "database_deleted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('cleanup_pending','completed','failed')",
            name="ck_account_deletion_state",
        ),
        sa.CheckConstraint(
            "file_count >= 0 AND deleted_file_count >= 0 AND deleted_file_count <= file_count",
            name="ck_account_deletion_counts",
        ),
    )
    op.create_table(
        "account_deletion_file",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_operation_key",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("account_deletion_job.operation_key", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(80), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_error_code", sa.String(50)),
        sa.CheckConstraint("attempt_count >= 0", name="ck_account_deletion_file_attempts"),
        sa.UniqueConstraint("storage_key", name="uq_account_deletion_file_storage_key"),
    )
    op.create_index(
        "ix_account_deletion_file_next",
        "account_deletion_file",
        ["next_attempt_at", "id"],
    )
    op.execute("""DO $$ BEGIN
      IF current_user = 'aulas_owner'
        AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_runtime')
        AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_worker') THEN
        GRANT SELECT, INSERT, UPDATE ON account_deletion_job TO aulas_runtime;
        GRANT SELECT, INSERT, UPDATE, DELETE ON account_deletion_file TO aulas_runtime;
        GRANT USAGE ON SEQUENCE account_deletion_file_id_seq TO aulas_runtime;
        GRANT SELECT, UPDATE ON account_deletion_job TO aulas_worker;
        GRANT SELECT, UPDATE, DELETE ON account_deletion_file TO aulas_worker;
      END IF;
    END $$""")


def downgrade() -> None:
    remaining = (
        op.get_bind().execute(sa.text("SELECT count(*) FROM account_deletion_job")).scalar_one()
    )
    if remaining:
        raise RuntimeError(
            "Existem recibos de exclusao de conta; preserve-os ou restaure em ambiente isolado."
        )
    op.drop_index("ix_account_deletion_file_next", table_name="account_deletion_file")
    op.drop_table("account_deletion_file")
    op.drop_table("account_deletion_job")
