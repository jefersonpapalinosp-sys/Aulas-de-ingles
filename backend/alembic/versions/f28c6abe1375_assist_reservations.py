"""Sprint 39F: reservas de cota independentes de resultados apagáveis."""

import sqlalchemy as sa

from alembic import op

revision = "f28c6abe1375"
down_revision = "e17b5fad0264"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assist_reservation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_key", sa.String(80), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("modality", sa.String(20), nullable=False),
        sa.Column("provider_key", sa.String(64), nullable=False, unique=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(50)),
        sa.Column("cost_microusd", sa.Integer(), nullable=False),
        sa.Column("cost_known", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "request_key", name="uq_assist_user_request"),
        sa.CheckConstraint("modality IN ('writing','transcription')", name="ck_assist_modality"),
        sa.CheckConstraint("state IN ('reserved','consumed','released')", name="ck_assist_state"),
        sa.CheckConstraint("cost_microusd >= 0", name="ck_assist_cost"),
        sa.CheckConstraint("expires_at > created_at", name="ck_assist_expiry"),
    )
    op.create_index("ix_assist_user_created", "assist_reservation", ["user_id", "created_at"])
    op.create_index("ix_assist_state_expiry", "assist_reservation", ["state", "expires_at"])
    for table in ("writing_feedback", "transcription_job"):
        op.add_column(table, sa.Column("assist_reservation_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_assist",
            table,
            "assist_reservation",
            ["assist_reservation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_unique_constraint(f"uq_{table}_assist", table, ["assist_reservation_id"])
    # Não inventa momento de despacho. Preserva o consumo legado observável,
    # inclusive falhas; não é possível recuperar resultados apagados antes daqui.
    op.execute("""
        INSERT INTO assist_reservation
          (user_id, request_key, fingerprint, modality, provider_key, state, reason,
           cost_microusd, cost_known, created_at, expires_at)
        SELECT user_id, 'legacy-writing:' || id, repeat('0',64), 'writing',
          'legacy-writing:' || id, 'consumed', 'legacy_observed', assisted_cost_microusd,
          analysis_mode = 'assisted' AND assisted_cost_microusd > 0,
          created_at, created_at + interval '15 minutes'
        FROM writing_feedback WHERE provider IS NOT NULL
    """)
    op.execute("""
        UPDATE writing_feedback f SET assist_reservation_id = r.id
          FROM assist_reservation r WHERE r.request_key = 'legacy-writing:' || f.id
    """)
    op.execute("""
        INSERT INTO assist_reservation
          (user_id, request_key, fingerprint, modality, provider_key, state, reason,
           cost_microusd, cost_known, created_at, expires_at)
        SELECT user_id, 'legacy-transcription:' || id, repeat('0',64), 'transcription',
          idempotency_key, 'consumed', 'legacy_observed', cost_microusd,
          status = 'completed' AND cost_microusd > 0,
          requested_at, requested_at + interval '15 minutes'
        FROM transcription_job
    """)
    op.execute("""
        UPDATE transcription_job j SET assist_reservation_id = r.id
          FROM assist_reservation r WHERE r.request_key = 'legacy-transcription:' || j.id
    """)
    op.execute("""DO $$ BEGIN
        IF current_user = 'aulas_owner' AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_runtime') THEN
            GRANT SELECT, INSERT, UPDATE ON assist_reservation TO aulas_runtime;
            GRANT USAGE ON SEQUENCE assist_reservation_id_seq TO aulas_runtime;
            GRANT SELECT, UPDATE ON assist_reservation TO aulas_worker;
        END IF;
    END $$""")


def downgrade() -> None:
    raise RuntimeError("Sprint 39F: preserve o ledger de consumo. Restaure em base isolada.")
