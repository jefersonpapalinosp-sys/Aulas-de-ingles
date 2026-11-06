"""Sprint 56: limites persistidos; validar em revisão separada para liberar o lock."""

from alembic import op

revision = "a56b1c8d9004"
down_revision = "f53a1b8c9003"
branch_labels = None
depends_on = None

CHECKS = [
    [
        "transcription_job",
        "ck_transcription_provider_size",
        "length(transcript_text) <= 5000 AND (words IS NULL OR words = 'null'::jsonb OR CASE WHEN jsonb_typeof(words) = 'array' THEN jsonb_array_length(words) <= 300 AND octet_length(words::text) <= 262144 ELSE false END)",
    ],
    [
        "dialogue_turn",
        "ck_dialogue_provider_size",
        "length(transcript) <= 5000 AND length(partner_text) <= 280 AND CASE WHEN jsonb_typeof(hints) = 'array' THEN jsonb_array_length(hints) <= 3 AND octet_length(hints::text) <= 4096 ELSE false END",
    ],
    [
        "writing_feedback",
        "ck_writing_provider_size",
        "length(assisted_summary) <= 1000 AND (assisted_suggestions IS NULL OR assisted_suggestions = 'null'::jsonb OR CASE WHEN jsonb_typeof(assisted_suggestions) = 'array' THEN jsonb_array_length(assisted_suggestions) <= 12 AND octet_length(assisted_suggestions::text) <= 32768 ELSE false END)",
    ],
]


def upgrade() -> None:
    for table, name, condition in CHECKS:
        op.create_check_constraint(name, table, condition, postgresql_not_valid=True)


def downgrade() -> None:
    for table, name, _ in reversed(CHECKS):
        op.drop_constraint(name, table, type_="check")
