"""gravacoes de speaking

Revision ID: a46d7f02e358
Revises: f35b8e91c247
Create Date: 2026-10-07 23:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a46d7f02e358"
down_revision: str | None = "f35b8e91c247"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "speaking_attempt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transcript_cue_id", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("self_rating", sa.String(length=20), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("storage_key", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("duration_ms > 0", name="ck_speaking_duration_positive"),
        sa.CheckConstraint("duration_ms <= 30000", name="ck_speaking_duration_limit"),
        sa.CheckConstraint("file_size IS NULL OR file_size > 0", name="ck_speaking_file_size_positive"),
        sa.ForeignKeyConstraint(["transcript_cue_id"], ["transcript_cue.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(op.f("ix_speaking_attempt_transcript_cue_id"), "speaking_attempt", ["transcript_cue_id"])
    op.create_index(op.f("ix_speaking_attempt_user_id"), "speaking_attempt", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_speaking_attempt_user_id"), table_name="speaking_attempt")
    op.drop_index(op.f("ix_speaking_attempt_transcript_cue_id"), table_name="speaking_attempt")
    op.drop_table("speaking_attempt")
