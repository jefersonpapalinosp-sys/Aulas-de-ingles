"""Sprint 39A: retomada por revisão e intervalos ativos; sem redistribuir legado."""

import sqlalchemy as sa

from alembic import op

revision = "e17b5fad0264"
down_revision = "d06a4e9cb153"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("operation_key", sa.String(36)),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("changed_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("media_progress", column)
    op.create_check_constraint("ck_media_progress_revision", "media_progress", "revision >= 0")
    op.create_check_constraint(
        "ck_media_completed_zero", "media_progress", "NOT completed OR position_seconds = 0"
    )
    op.add_column(
        "study_plan", sa.Column("timezone", sa.String(80), nullable=False, server_default="UTC")
    )
    op.create_table(
        "study_activity_session",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lesson_id",
            sa.Integer(),
            sa.ForeignKey("lesson.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_study_activity_session_user_id", "study_activity_session", ["user_id"])
    op.create_table(
        "study_activity_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("study_activity_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation_key", sa.String(36), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("credited_ms", sa.Integer(), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "operation_key", name="uq_activity_event_key"),
        sa.CheckConstraint("duration_ms BETWEEN 1 AND 30000", name="ck_activity_duration"),
        sa.CheckConstraint("credited_ms BETWEEN 0 AND duration_ms", name="ck_activity_credit"),
    )
    op.create_index("ix_study_activity_event_user_id", "study_activity_event", ["user_id"])
    op.create_index("ix_study_activity_event_session_id", "study_activity_event", ["session_id"])
    op.create_table(
        "study_active_interval",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("study_activity_event.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lesson_id",
            sa.Integer(),
            sa.ForeignKey("lesson.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ends_at > starts_at AND ends_at <= starts_at + interval '30 seconds'",
            name="ck_active_interval_duration",
        ),
    )
    op.create_index("ix_active_interval_user_end", "study_active_interval", ["user_id", "ends_at"])
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_runtime')
           AND current_user = 'aulas_owner' THEN
            GRANT SELECT, INSERT ON study_activity_session, study_activity_event, study_active_interval TO aulas_runtime;
            GRANT USAGE ON SEQUENCE study_activity_event_id_seq, study_active_interval_id_seq TO aulas_runtime;
        END IF;
    END $$""")


def downgrade() -> None:
    raise RuntimeError("Sprint 39: preserve eventos e tombstones. Restaure em base isolada.")
