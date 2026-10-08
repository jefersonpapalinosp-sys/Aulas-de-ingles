"""laboratorio de exercicios

Revision ID: d4e7a1b8c320
Revises: c1d4e8f6a290
Create Date: 2026-10-08 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e7a1b8c320"
down_revision: str | None = "c1d4e8f6a290"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exercise",
        sa.Column("objective", sa.String(length=20), server_default="apply", nullable=False),
    )
    op.execute("UPDATE exercise SET objective = 'listen' WHERE skill = 'listening'")
    op.execute(
        "UPDATE exercise SET objective = 'correct' "
        "WHERE skill != 'listening' AND activity_type = 'transformation'"
    )
    op.execute(
        "UPDATE exercise SET objective = 'recognize' "
        "WHERE skill != 'listening' AND activity_type = 'multiple_choice'"
    )
    op.create_check_constraint(
        "ck_exercise_objective",
        "exercise",
        "objective IN ('recognize', 'apply', 'correct', 'produce', 'listen')",
    )

    op.create_table(
        "practice_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("source_session_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("activity_type", sa.String(length=40), nullable=True),
        sa.Column("skill", sa.String(length=40), nullable=True),
        sa.Column("objective", sa.String(length=20), nullable=True),
        sa.Column("lesson_version", sa.Integer(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("current_position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("state_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_state_key", sa.String(length=36), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('guided', 'quick', 'mistakes')", name="ck_practice_session_mode"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="ck_practice_session_status",
        ),
        sa.CheckConstraint(
            "current_position >= 0", name="ck_practice_session_position_nonnegative"
        ),
        sa.CheckConstraint("total_items > 0", name="ck_practice_session_total_positive"),
        sa.CheckConstraint("state_revision > 0", name="ck_practice_session_revision_positive"),
        sa.CheckConstraint(
            "objective IS NULL OR objective IN "
            "('recognize', 'apply', 'correct', 'produce', 'listen')",
            name="ck_practice_session_objective",
        ),
        sa.ForeignKeyConstraint(["lesson_id"], ["lesson.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_session_id"], ["practice_session.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_practice_session_user_idempotency"
        ),
    )
    op.create_index(
        op.f("ix_practice_session_user_id"), "practice_session", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_practice_session_lesson_id"),
        "practice_session",
        ["lesson_id"],
        unique=False,
    )
    op.create_index(
        "uq_practice_session_active_user_lesson",
        "practice_session",
        ["user_id", "lesson_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "practice_session_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("practice_session_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("first_try_correct", sa.Boolean(), nullable=True),
        sa.Column("highest_hint_level", sa.Integer(), server_default="0", nullable=False),
        sa.Column("answer_revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("position >= 0", name="ck_practice_item_position_nonnegative"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_practice_item_attempts_nonnegative"),
        sa.CheckConstraint("highest_hint_level >= 0", name="ck_practice_item_hint_nonnegative"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercise.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["practice_session_id"], ["practice_session.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "practice_session_id",
            "exercise_id",
            name="uq_practice_item_session_exercise",
        ),
        sa.UniqueConstraint(
            "practice_session_id", "position", name="uq_practice_item_session_position"
        ),
    )
    op.create_index(
        op.f("ix_practice_session_item_practice_session_id"),
        "practice_session_item",
        ["practice_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_practice_session_item_exercise_id"),
        "practice_session_item",
        ["exercise_id"],
        unique=False,
    )

    op.add_column(
        "exercise_attempt",
        sa.Column("practice_session_item_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_exercise_attempt_practice_session_item_id"),
        "exercise_attempt",
        ["practice_session_item_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_exercise_attempt_practice_item",
        "exercise_attempt",
        "practice_session_item",
        ["practice_session_item_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_exercise_attempt_practice_item", "exercise_attempt", type_="foreignkey")
    op.drop_index(
        op.f("ix_exercise_attempt_practice_session_item_id"),
        table_name="exercise_attempt",
    )
    op.drop_column("exercise_attempt", "practice_session_item_id")
    op.drop_index(op.f("ix_practice_session_item_exercise_id"), table_name="practice_session_item")
    op.drop_index(
        op.f("ix_practice_session_item_practice_session_id"),
        table_name="practice_session_item",
    )
    op.drop_table("practice_session_item")
    op.drop_index("uq_practice_session_active_user_lesson", table_name="practice_session")
    op.drop_index(op.f("ix_practice_session_lesson_id"), table_name="practice_session")
    op.drop_index(op.f("ix_practice_session_user_id"), table_name="practice_session")
    op.drop_table("practice_session")
    op.drop_constraint("ck_exercise_objective", "exercise", type_="check")
    op.drop_column("exercise", "objective")
