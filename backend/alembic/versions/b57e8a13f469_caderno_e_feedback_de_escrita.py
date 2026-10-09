"""caderno e feedback de escrita

Revision ID: b57e8a13f469
Revises: a46d7f02e358
Create Date: 2026-10-08 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b57e8a13f469"
down_revision: str | None = "a46d7f02e358"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notebook_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lesson_id"], ["lesson.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notebook_entry_lesson_id"), "notebook_entry", ["lesson_id"])
    op.create_index(op.f("ix_notebook_entry_user_id"), "notebook_entry", ["user_id"])
    op.create_table(
        "writing_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("prompt_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("sentence_count", sa.Integer(), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["prompt_id"], ["writing_prompt.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_writing_feedback_prompt_id"), "writing_feedback", ["prompt_id"])
    op.create_index(op.f("ix_writing_feedback_user_id"), "writing_feedback", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_writing_feedback_user_id"), table_name="writing_feedback")
    op.drop_index(op.f("ix_writing_feedback_prompt_id"), table_name="writing_feedback")
    op.drop_table("writing_feedback")
    op.drop_index(op.f("ix_notebook_entry_user_id"), table_name="notebook_entry")
    op.drop_index(op.f("ix_notebook_entry_lesson_id"), table_name="notebook_entry")
    op.drop_table("notebook_entry")
