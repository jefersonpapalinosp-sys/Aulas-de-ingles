"""checkpoint curricular 40-44

Revision ID: f62a8d4c1e90
Revises: e5f8b2c9d431
Create Date: 2026-10-08 23:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f62a8d4c1e90"
down_revision: str | None = "e5f8b2c9d431"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course_review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("source_title", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_note", sa.String(length=500), nullable=False),
        sa.Column("intro", sa.Text(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("review_lesson_number", sa.Integer(), nullable=False),
        sa.Column("listening_lesson_number", sa.Integer(), nullable=True),
        sa.Column("listening_media_position", sa.Integer(), nullable=True),
        sa.CheckConstraint("position > 0", name="ck_course_review_position_positive"),
        sa.CheckConstraint(
            "estimated_minutes > 0", name="ck_course_review_minutes_positive"
        ),
        sa.CheckConstraint(
            "content_version > 0", name="ck_course_review_version_positive"
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'published', 'archived')",
            name="ck_course_review_status",
        ),
        sa.CheckConstraint(
            "source_kind IN ('official', 'authorial', 'mixed')",
            name="ck_course_review_source_kind",
        ),
        sa.ForeignKeyConstraint(["unit_id"], ["course_unit.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unit_id", name="uq_course_review_unit"),
        sa.UniqueConstraint("unit_id", "slug", name="uq_course_review_unit_slug"),
    )
    op.create_index(op.f("ix_course_review_unit_id"), "course_review", ["unit_id"])

    op.create_table(
        "course_review_question",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("activity_type", sa.String(length=30), nullable=False),
        sa.Column("skill", sa.String(length=30), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("accepted_answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("lesson_numbers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "position > 0", name="ck_course_review_question_position_positive"
        ),
        sa.CheckConstraint(
            "activity_type IN ('multiple_choice', 'short_answer')",
            name="ck_course_review_question_activity_type",
        ),
        sa.CheckConstraint(
            "skill IN ('grammar', 'listening', 'vocabulary')",
            name="ck_course_review_question_skill",
        ),
        sa.ForeignKeyConstraint(["review_id"], ["course_review.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "review_id", "position", name="uq_course_review_question_position"
        ),
    )
    op.create_index(
        op.f("ix_course_review_question_review_id"),
        "course_review_question",
        ["review_id"],
    )

    op.create_table(
        "course_review_attempt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=36), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "content_version > 0", name="ck_course_review_attempt_version_positive"
        ),
        sa.CheckConstraint(
            "score >= 0", name="ck_course_review_attempt_score_nonnegative"
        ),
        sa.CheckConstraint("total > 0", name="ck_course_review_attempt_total_positive"),
        sa.CheckConstraint(
            "score <= total", name="ck_course_review_attempt_score_within_total"
        ),
        sa.ForeignKeyConstraint(["review_id"], ["course_review.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_course_review_attempt_user_idempotency"
        ),
    )
    op.create_index(
        op.f("ix_course_review_attempt_review_id"),
        "course_review_attempt",
        ["review_id"],
    )
    op.create_index(
        op.f("ix_course_review_attempt_user_id"),
        "course_review_attempt",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_course_review_attempt_user_id"), table_name="course_review_attempt"
    )
    op.drop_index(
        op.f("ix_course_review_attempt_review_id"), table_name="course_review_attempt"
    )
    op.drop_table("course_review_attempt")
    op.drop_index(
        op.f("ix_course_review_question_review_id"), table_name="course_review_question"
    )
    op.drop_table("course_review_question")
    op.drop_index(op.f("ix_course_review_unit_id"), table_name="course_review")
    op.drop_table("course_review")
