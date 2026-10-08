"""transcricao e atividade de listening

Revision ID: c83e1a7f209b
Revises: b72c9d10e431
Create Date: 2026-10-07 21:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c83e1a7f209b"
down_revision: str | None = "b72c9d10e431"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lesson_media", sa.Column("listening_exercise_position", sa.Integer(), nullable=True)
    )
    op.create_table(
        "transcript_cue",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("speaker", sa.String(length=80), nullable=False),
        sa.Column("text_en", sa.Text(), nullable=False),
        sa.Column("text_pt", sa.Text(), nullable=False),
        sa.CheckConstraint("start_seconds >= 0", name="ck_transcript_start_nonnegative"),
        sa.CheckConstraint("end_seconds > start_seconds", name="ck_transcript_end_after_start"),
        sa.ForeignKeyConstraint(["media_id"], ["lesson_media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("media_id", "position", name="uq_transcript_media_position"),
    )
    op.create_index(op.f("ix_transcript_cue_media_id"), "transcript_cue", ["media_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_transcript_cue_media_id"), table_name="transcript_cue")
    op.drop_table("transcript_cue")
    op.drop_column("lesson_media", "listening_exercise_position")
