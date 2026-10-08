"""motor de atividades e feedback

Revision ID: f35b8e91c247
Revises: e24a7d6c5b19
Create Date: 2026-10-07 23:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f35b8e91c247"
down_revision: str | None = "e24a7d6c5b19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exercise",
        sa.Column("activity_type", sa.String(length=40), server_default="gap_fill", nullable=False),
    )
    op.add_column(
        "exercise",
        sa.Column("skill", sa.String(length=40), server_default="grammar", nullable=False),
    )
    op.add_column(
        "exercise",
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "exercise_attempt",
        sa.Column("idempotency_key", sa.String(length=36), nullable=True),
    )
    op.create_unique_constraint(
        "uq_attempt_user_idempotency",
        "exercise_attempt",
        ["user_id", "idempotency_key"],
    )
    op.create_table(
        "exercise_hint",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.CheckConstraint("level > 0", name="ck_exercise_hint_level_positive"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercise.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exercise_id", "level", name="uq_exercise_hint_level"),
    )
    op.create_index(op.f("ix_exercise_hint_exercise_id"), "exercise_hint", ["exercise_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_exercise_hint_exercise_id"), table_name="exercise_hint")
    op.drop_table("exercise_hint")
    op.drop_constraint("uq_attempt_user_idempotency", "exercise_attempt", type_="unique")
    op.drop_column("exercise_attempt", "idempotency_key")
    op.drop_column("exercise", "options")
    op.drop_column("exercise", "skill")
    op.drop_column("exercise", "activity_type")
