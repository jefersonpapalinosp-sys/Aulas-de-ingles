"""Sprint 56: valida limites sem o lock exclusivo da criação do CHECK."""

from alembic import op

revision = "b56b1c8d9005"
down_revision = "a56b1c8d9004"
branch_labels = None
depends_on = None

CONSTRAINTS = [
    ["transcription_job", "ck_transcription_provider_size"],
    ["dialogue_turn", "ck_dialogue_provider_size"],
    ["writing_feedback", "ck_writing_provider_size"],
]


def upgrade() -> None:
    for table, name in CONSTRAINTS:
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def downgrade() -> None:
    # Validação não altera dados; manter CHECK validado é seguro na revisão anterior.
    pass
