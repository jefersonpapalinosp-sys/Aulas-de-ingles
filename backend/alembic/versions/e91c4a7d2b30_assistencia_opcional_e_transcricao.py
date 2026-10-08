"""assistencia opcional e transcricao

Revision ID: e91c4a7d2b30
Revises: d79a1c35b681
Create Date: 2026-10-08 04:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e91c4a7d2b30"
down_revision: str | None = "d79a1c35b681"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transcription_job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("speaking_attempt_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("words", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("mean_confidence", sa.Float(), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("low_confidence", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("cost_microusd", sa.Integer(), nullable=False),
        sa.Column("human_rating", sa.String(length=20), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cost_microusd >= 0", name="ck_transcription_cost_nonnegative"),
        sa.CheckConstraint(
            "mean_confidence IS NULL OR (mean_confidence >= 0 AND mean_confidence <= 1)",
            name="ck_transcription_confidence",
        ),
        sa.CheckConstraint(
            "similarity_score IS NULL OR (similarity_score >= 0 AND similarity_score <= 1)",
            name="ck_transcription_similarity",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_transcription_job_status",
        ),
        sa.ForeignKeyConstraint(
            ["speaking_attempt_id"], ["speaking_attempt.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transcription_job_expires_at"), "transcription_job", ["expires_at"])
    op.create_index(
        op.f("ix_transcription_job_speaking_attempt_id"),
        "transcription_job",
        ["speaking_attempt_id"],
        unique=True,
    )
    op.create_index(op.f("ix_transcription_job_status"), "transcription_job", ["status"])
    op.create_index(op.f("ix_transcription_job_user_id"), "transcription_job", ["user_id"])

    op.add_column(
        "writing_feedback",
        sa.Column(
            "analysis_mode", sa.String(length=20), server_default="deterministic", nullable=False
        ),
    )
    op.add_column("writing_feedback", sa.Column("provider", sa.String(length=80), nullable=True))
    op.add_column("writing_feedback", sa.Column("assisted_summary", sa.Text(), nullable=True))
    op.add_column(
        "writing_feedback",
        sa.Column("assisted_suggestions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("writing_feedback", sa.Column("assisted_confidence", sa.Float(), nullable=True))
    op.add_column(
        "writing_feedback",
        sa.Column("assisted_cost_microusd", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "writing_feedback", sa.Column("assisted_error_code", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "writing_feedback", sa.Column("human_rating", sa.String(length=20), nullable=True)
    )
    op.create_check_constraint(
        "ck_writing_feedback_analysis_mode",
        "writing_feedback",
        "analysis_mode IN ('deterministic', 'assisted', 'fallback')",
    )
    op.create_check_constraint(
        "ck_writing_feedback_confidence",
        "writing_feedback",
        "assisted_confidence IS NULL OR (assisted_confidence >= 0 AND assisted_confidence <= 1)",
    )
    op.create_check_constraint(
        "ck_writing_feedback_cost_nonnegative", "writing_feedback", "assisted_cost_microusd >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_writing_feedback_cost_nonnegative", "writing_feedback", type_="check")
    op.drop_constraint("ck_writing_feedback_confidence", "writing_feedback", type_="check")
    op.drop_constraint("ck_writing_feedback_analysis_mode", "writing_feedback", type_="check")
    for column in [
        "human_rating",
        "assisted_error_code",
        "assisted_cost_microusd",
        "assisted_confidence",
        "assisted_suggestions",
        "assisted_summary",
        "provider",
        "analysis_mode",
    ]:
        op.drop_column("writing_feedback", column)
    op.drop_index(op.f("ix_transcription_job_user_id"), table_name="transcription_job")
    op.drop_index(op.f("ix_transcription_job_status"), table_name="transcription_job")
    op.drop_index(op.f("ix_transcription_job_speaking_attempt_id"), table_name="transcription_job")
    op.drop_index(op.f("ix_transcription_job_expires_at"), table_name="transcription_job")
    op.drop_table("transcription_job")
