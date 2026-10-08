"""workspace de escrita

Revision ID: e24a7d6c5b19
Revises: d91f4c2b8a60
Create Date: 2026-10-07 22:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e24a7d6c5b19"
down_revision: str | None = "d91f4c2b8a60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "writing_prompt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("min_words", sa.Integer(), nullable=False),
        sa.Column("min_sentences", sa.Integer(), nullable=False),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lesson.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "position", name="uq_writing_prompt_lesson_position"),
    )
    op.create_index(op.f("ix_writing_prompt_lesson_id"), "writing_prompt", ["lesson_id"])
    op.create_table(
        "writing_draft",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("prompt_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["prompt_id"], ["writing_prompt.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "prompt_id", name="uq_writing_draft_user_prompt"),
    )
    op.create_index(op.f("ix_writing_draft_prompt_id"), "writing_draft", ["prompt_id"])
    op.create_index(op.f("ix_writing_draft_user_id"), "writing_draft", ["user_id"])
    op.create_table(
        "writing_revision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["draft_id"], ["writing_draft.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_id", "version", name="uq_writing_revision_draft_version"),
    )
    op.create_index(op.f("ix_writing_revision_draft_id"), "writing_revision", ["draft_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_writing_revision_draft_id"), table_name="writing_revision")
    op.drop_table("writing_revision")
    op.drop_index(op.f("ix_writing_draft_user_id"), table_name="writing_draft")
    op.drop_index(op.f("ix_writing_draft_prompt_id"), table_name="writing_draft")
    op.drop_table("writing_draft")
    op.drop_index(op.f("ix_writing_prompt_lesson_id"), table_name="writing_prompt")
    op.drop_table("writing_prompt")
