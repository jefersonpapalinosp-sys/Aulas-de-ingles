"""Sprint 38: revisões, recibos e famílias. Preflight não altera dados inválidos.

Revision ID: d06a4e9cb153
Revises: c95f3d8ba042
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d06a4e9cb153"
down_revision = "c95f3d8ba042"
branch_labels = None
depends_on = None

CHECKS = (
    (
        "study_session_progress",
        "ck_study_step",
        "current_step IN ('preparar','assistir','estudar','praticar','revisar')",
    ),
    ("study_session_progress", "ck_study_seconds", "total_seconds >= 0"),
    (
        "study_session_progress",
        "ck_study_completed_steps",
        'jsonb_typeof(completed_steps) = \'array\' AND completed_steps <@ \'["preparar","assistir","estudar","praticar","revisar"]\'::jsonb',
    ),
    (
        "step_progress",
        "ck_step_name",
        "step IN ('preparar','assistir','estudar','praticar','revisar')",
    ),
    (
        "review_item",
        "ck_review_counters",
        "interval_days >= 0 AND repetitions >= 0 AND lapses >= 0 AND ease_factor >= 1.3",
    ),
    (
        "notebook_entry",
        "ck_notebook_kind",
        "kind IN ('note','favorite_phrase','personal_example','recurring_error','teacher_question')",
    ),
    ("speaking_attempt", "ck_speaking_status", "status IN ('pending','ready')"),
)


def upgrade() -> None:
    bind = op.get_bind()
    invalid = {}
    for table, name, expression in CHECKS:
        count = bind.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE NOT ({expression})")
        ).scalar_one()
        if count:
            invalid[name] = count
    if invalid:
        raise RuntimeError(f"Preflight Sprint 38 recusado (somente contagens): {invalid}")
    for table in ("writing_draft", "study_session_progress", "review_item"):
        op.add_column(
            table, sa.Column("revision", sa.Integer(), nullable=False, server_default="0")
        )
        op.create_check_constraint(f"ck_{table}_revision", table, "revision >= 0")
    op.add_column("refresh_session", sa.Column("family_id", sa.String(32), nullable=True))
    op.add_column("refresh_session", sa.Column("successor_jti", sa.String(32), nullable=True))
    # Raízes de sessões existentes são dedutíveis; não inventamos sucessores históricos.
    bind.execute(sa.text("UPDATE refresh_session SET family_id = jti"))
    op.alter_column("refresh_session", "family_id", nullable=False)
    op.create_index("ix_refresh_session_family_id", "refresh_session", ["family_id"])
    op.create_table(
        "review_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("review_item.id", ondelete="SET NULL")),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("quality", sa.Integer(), nullable=False),
        sa.Column("algorithm_version", sa.String(30), nullable=False),
        sa.Column("before_state", postgresql.JSONB(), nullable=False),
        sa.Column("after_state", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_review_event_key"),
        sa.CheckConstraint("quality BETWEEN 0 AND 5", name="ck_review_event_quality"),
    )
    op.create_index("ix_review_event_user_id", "review_event", ["user_id"])
    op.create_table(
        "auth_rate_bucket",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.Integer(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.CheckConstraint("count > 0", name="ck_auth_rate_count"),
    )
    for table, name, expression in CHECKS:
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID")
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_runtime')
           AND current_user = 'aulas_owner' THEN
            GRANT SELECT, INSERT ON review_event TO aulas_runtime;
            GRANT USAGE ON SEQUENCE review_event_id_seq TO aulas_runtime;
            GRANT SELECT, INSERT, UPDATE, DELETE ON auth_rate_bucket TO aulas_runtime;
        END IF;
    END $$""")


def downgrade() -> None:
    # Revisões/recibos são evidências. Nenhum downgrade destrutivo implícito.
    raise RuntimeError("Sprint 38: downgrade bloqueado. Restaure backup validado em base separada.")
