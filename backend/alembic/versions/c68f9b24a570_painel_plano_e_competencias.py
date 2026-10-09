"""painel, plano semanal e competências

Revision ID: c68f9b24a570
Revises: b57e8a13f469
Create Date: 2026-10-08 02:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c68f9b24a570"
down_revision: str | None = "b57e8a13f469"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "study_session_progress",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "study_session_progress",
        sa.Column("total_seconds", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "study_session_progress",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "study_plan",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("weekly_minutes", sa.Integer(), nullable=False),
        sa.Column("preferred_days", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("goal", sa.String(length=200), nullable=False),
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
        sa.CheckConstraint(
            "weekly_minutes >= 30 AND weekly_minutes <= 600",
            name="ck_study_plan_weekly_minutes",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_study_plan_user"),
    )
    op.create_index(op.f("ix_study_plan_user_id"), "study_plan", ["user_id"])

    op.create_table(
        "step_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("study_session_id", sa.Integer(), nullable=False),
        sa.Column("step", sa.String(length=20), nullable=False),
        sa.Column("seconds_spent", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("seconds_spent >= 0", name="ck_step_progress_seconds_nonnegative"),
        sa.ForeignKeyConstraint(
            ["study_session_id"], ["study_session_progress.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_session_id", "step", name="uq_step_progress_session_step"),
    )
    op.create_index(
        op.f("ix_step_progress_study_session_id"),
        "step_progress",
        ["study_session_id"],
    )

    op.create_table(
        "skill_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("skill", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_skill_evidence_score"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_type", "source_id", name="uq_skill_evidence_source"),
    )
    op.create_index(op.f("ix_skill_evidence_skill"), "skill_evidence", ["skill"])
    op.create_index(op.f("ix_skill_evidence_user_id"), "skill_evidence", ["user_id"])

    # Preserva as evidências produzidas antes desta sprint.
    op.execute(
        """
        INSERT INTO skill_evidence (user_id, skill, source_type, source_id, score, occurred_at)
        SELECT ea.user_id, e.skill, 'exercise_attempt', ea.id,
               CASE WHEN ea.correct THEN 1.0 ELSE 0.0 END, ea.created_at
          FROM exercise_attempt ea
          JOIN exercise e ON e.id = ea.exercise_id
        """
    )
    op.execute(
        """
        INSERT INTO skill_evidence (user_id, skill, source_type, source_id, score, occurred_at)
        SELECT user_id, 'writing', 'writing_feedback', id,
               CASE WHEN ready THEN 1.0 ELSE 0.5 END, created_at
          FROM writing_feedback
        """
    )
    op.execute(
        """
        INSERT INTO skill_evidence (user_id, skill, source_type, source_id, score, occurred_at)
        SELECT user_id, 'speaking', 'speaking_attempt', id,
               CASE self_rating
                 WHEN 'confident' THEN 1.0
                 WHEN 'almost' THEN 0.7
                 WHEN 'repeat' THEN 0.35
                 ELSE 0.5
               END,
               created_at
          FROM speaking_attempt
         WHERE status = 'ready'
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_skill_evidence_user_id"), table_name="skill_evidence")
    op.drop_index(op.f("ix_skill_evidence_skill"), table_name="skill_evidence")
    op.drop_table("skill_evidence")
    op.drop_index(op.f("ix_step_progress_study_session_id"), table_name="step_progress")
    op.drop_table("step_progress")
    op.drop_index(op.f("ix_study_plan_user_id"), table_name="study_plan")
    op.drop_table("study_plan")
    op.drop_column("study_session_progress", "completed_at")
    op.drop_column("study_session_progress", "total_seconds")
    op.drop_column("study_session_progress", "started_at")
