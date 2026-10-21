"""DB-45: schema aditivo do parceiro de conversa

Duas tabelas novas (`speaking_dialogue`, `dialogue_turn`), a modalidade
`conversation` em `ck_assist_modality` e grants por coluna: a API só altera a
avaliação humana de um turno; o worker preenche o resultado e nunca apaga.
Nenhuma tabela existente muda além da constraint ampliada.

Revision ID: e3a1c7d9b250
Revises: d2b7e4c9a150
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e3a1c7d9b250"
down_revision: str | None = "d2b7e4c9a150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODALITIES_BEFORE = "modality IN ('writing','transcription')"
MODALITIES_AFTER = "modality IN ('writing','transcription','conversation')"

# Espelho de ops/roles_policy.sql. Só executa quando a migration roda como
# aulas_owner com os papéis provisionados (laboratório e produção com papéis).
GRANTS = """DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_runtime')
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_worker')
       AND current_user = 'aulas_owner' THEN
        GRANT SELECT, INSERT, DELETE ON speaking_dialogue TO aulas_runtime;
        GRANT UPDATE (state, ended_at, provider_name) ON speaking_dialogue TO aulas_runtime;
        GRANT SELECT, INSERT ON dialogue_turn TO aulas_runtime;
        GRANT UPDATE (human_rating) ON dialogue_turn TO aulas_runtime;
        GRANT USAGE ON SEQUENCE speaking_dialogue_id_seq, dialogue_turn_id_seq TO aulas_runtime;
        GRANT SELECT ON speaking_dialogue TO aulas_worker;
        GRANT UPDATE (state, ended_at) ON speaking_dialogue TO aulas_worker;
        GRANT SELECT, INSERT ON dialogue_turn TO aulas_worker;
        GRANT UPDATE (state, transcription_job_id, transcript, checks, partner_text, hints,
                      confidence, fallback, cost_microusd, error_code, completed_at)
            ON dialogue_turn TO aulas_worker;
        GRANT USAGE ON SEQUENCE dialogue_turn_id_seq TO aulas_worker;
    END IF;
END $$"""


def upgrade() -> None:
    op.create_table(
        "speaking_dialogue",
        sa.Column("id", sa.Integer(), primary_key=True),
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
        sa.Column("operation_key", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("partner_speaker", sa.String(80)),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("provider_name", sa.String(80)),
        sa.Column("rubric_version", sa.String(40), nullable=False),
        sa.Column("turn_limit", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "operation_key", name="uq_dialogue_user_operation"),
        sa.CheckConstraint("mode IN ('script','guided','free_unit')", name="ck_dialogue_mode"),
        sa.CheckConstraint("state IN ('active','completed','abandoned')", name="ck_dialogue_state"),
        sa.CheckConstraint("turn_limit > 0 AND turn_limit <= 50", name="ck_dialogue_turn_limit"),
        sa.CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_dialogue_ended"),
    )
    op.create_index(op.f("ix_speaking_dialogue_lesson_id"), "speaking_dialogue", ["lesson_id"])
    op.create_index(
        "ix_dialogue_user_started", "speaking_dialogue", ["user_id", "started_at", "id"]
    )
    op.create_table(
        "dialogue_turn",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "dialogue_id",
            sa.Integer(),
            sa.ForeignKey("speaking_dialogue.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("input_kind", sa.String(20)),
        sa.Column(
            "speaking_attempt_id",
            sa.Integer(),
            sa.ForeignKey("speaking_attempt.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "transcription_job_id",
            sa.Integer(),
            sa.ForeignKey("transcription_job.id", ondelete="SET NULL"),
        ),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("transcript", sa.Text()),
        sa.Column(
            "checks",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("partner_text", sa.Text()),
        sa.Column(
            "hints",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confidence", sa.Float()),
        sa.Column("fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cost_microusd", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(50)),
        sa.Column("human_rating", sa.String(20)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dialogue_id", "position", name="uq_dialogue_turn_position"),
        sa.UniqueConstraint("speaking_attempt_id", name="uq_dialogue_turn_speaking_attempt"),
        sa.UniqueConstraint("transcription_job_id", name="uq_dialogue_turn_transcription_job"),
        sa.CheckConstraint("position > 0", name="ck_dialogue_turn_position"),
        sa.CheckConstraint("role IN ('student','partner')", name="ck_dialogue_turn_role"),
        sa.CheckConstraint(
            "(role = 'student') = (input_kind IS NOT NULL) "
            "AND (input_kind IS NULL OR input_kind IN ('audio','text'))",
            name="ck_dialogue_turn_input",
        ),
        sa.CheckConstraint(
            "state IN ('pending','completed','failed')", name="ck_dialogue_turn_state"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_dialogue_turn_confidence",
        ),
        sa.CheckConstraint("cost_microusd >= 0", name="ck_dialogue_turn_cost"),
        sa.CheckConstraint(
            "jsonb_typeof(checks) = 'object' AND jsonb_typeof(hints) = 'array'",
            name="ck_dialogue_turn_json",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_dialogue_turn_expiry"),
    )
    op.create_index(op.f("ix_dialogue_turn_user_id"), "dialogue_turn", ["user_id"])
    op.create_index(op.f("ix_dialogue_turn_expires_at"), "dialogue_turn", ["expires_at"])
    op.drop_constraint("ck_assist_modality", "assist_reservation", type_="check")
    op.create_check_constraint("ck_assist_modality", "assist_reservation", MODALITIES_AFTER)
    op.execute(GRANTS)


def downgrade() -> None:
    """Não destrutivo: só reverte quando não há diálogo, turno ou reserva de conversa."""

    bind = op.get_bind()
    counts = {
        name: int(bind.execute(sa.text(sql)).scalar_one())
        for name, sql in (
            ("dialogos", "SELECT count(*) FROM speaking_dialogue"),
            ("turnos", "SELECT count(*) FROM dialogue_turn"),
            (
                "reservas",
                "SELECT count(*) FROM assist_reservation WHERE modality = 'conversation'",
            ),
        )
    }
    if any(counts.values()):
        raise RuntimeError(
            "DB-45: downgrade bloqueado; turnos são evidência do aluno "
            f"({counts['dialogos']} diálogos, {counts['turnos']} turnos, "
            f"{counts['reservas']} reservas de conversa). Restaure somente em base isolada."
        )
    op.drop_constraint("ck_assist_modality", "assist_reservation", type_="check")
    op.create_check_constraint("ck_assist_modality", "assist_reservation", MODALITIES_BEFORE)
    op.drop_table("dialogue_turn")
    op.drop_table("speaking_dialogue")
