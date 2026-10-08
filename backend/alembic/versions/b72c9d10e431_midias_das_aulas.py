"""midias das aulas

Revision ID: b72c9d10e431
Revises: 436e2d910761
Create Date: 2026-10-07 20:46:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b72c9d10e431"
down_revision: str | None = "436e2d910761"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lesson_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["lesson_id"], ["lesson.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "position", name="uq_media_lesson_position"),
    )
    op.create_index(op.f("ix_lesson_media_lesson_id"), "lesson_media", ["lesson_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lesson_media_lesson_id"), table_name="lesson_media")
    op.drop_table("lesson_media")
