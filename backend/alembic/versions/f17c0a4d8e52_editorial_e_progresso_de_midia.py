"""editorial e progresso de midia

Revision ID: f17c0a4d8e52
Revises: e91c4a7d2b30
Create Date: 2026-10-08 00:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f17c0a4d8e52"
down_revision: str | None = "e91c4a7d2b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("publisher", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("license_note", sa.String(length=500), nullable=False),
        sa.Column("accessed_at", sa.Date(), nullable=False),
        sa.CheckConstraint("kind IN ('official', 'authorial')", name="ck_content_source_kind"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lesson.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "kind", name="uq_content_source_lesson_kind"),
    )
    op.create_index(op.f("ix_content_source_lesson_id"), "content_source", ["lesson_id"])

    op.create_table(
        "lesson_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("learning_strategy", sa.String(length=100), nullable=False),
        sa.Column("review_note", sa.String(length=500), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'reviewed', 'published')",
            name="ck_lesson_version_status",
        ),
        sa.CheckConstraint("version > 0", name="ck_lesson_version_positive"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lesson.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "version", name="uq_lesson_version_lesson_version"),
    )
    op.create_index(op.f("ix_lesson_version_lesson_id"), "lesson_version", ["lesson_id"])

    op.create_table(
        "media_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("position_seconds", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("position_seconds >= 0", name="ck_media_progress_nonnegative"),
        sa.ForeignKeyConstraint(["media_id"], ["lesson_media.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "media_id", name="uq_media_progress_user_media"),
    )
    op.create_index(op.f("ix_media_progress_media_id"), "media_progress", ["media_id"])
    op.create_index(op.f("ix_media_progress_user_id"), "media_progress", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_media_progress_user_id"), table_name="media_progress")
    op.drop_index(op.f("ix_media_progress_media_id"), table_name="media_progress")
    op.drop_table("media_progress")
    op.drop_index(op.f("ix_lesson_version_lesson_id"), table_name="lesson_version")
    op.drop_table("lesson_version")
    op.drop_index(op.f("ix_content_source_lesson_id"), table_name="content_source")
    op.drop_table("content_source")
