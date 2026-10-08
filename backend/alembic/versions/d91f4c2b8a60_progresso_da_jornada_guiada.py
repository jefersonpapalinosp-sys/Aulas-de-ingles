"""progresso da jornada guiada

Revision ID: d91f4c2b8a60
Revises: c83e1a7f209b
Create Date: 2026-10-07 21:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d91f4c2b8a60"
down_revision: str | None = "c83e1a7f209b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "study_session_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.String(length=20), nullable=False),
        sa.Column("completed_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lesson_id"], ["lesson.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "lesson_id", name="uq_study_session_user_lesson"),
    )
    op.create_index(
        op.f("ix_study_session_progress_lesson_id"),
        "study_session_progress",
        ["lesson_id"],
    )
    op.create_index(
        op.f("ix_study_session_progress_user_id"),
        "study_session_progress",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_study_session_progress_user_id"), table_name="study_session_progress")
    op.drop_index(op.f("ix_study_session_progress_lesson_id"), table_name="study_session_progress")
    op.drop_table("study_session_progress")
