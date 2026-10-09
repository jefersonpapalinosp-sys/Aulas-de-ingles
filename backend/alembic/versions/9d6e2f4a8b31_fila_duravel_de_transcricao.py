"""fila duravel de transcricao

Revision ID: 9d6e2f4a8b31
Revises: 8c5d1e3f7a90
Create Date: 2026-10-08 13:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d6e2f4a8b31"
down_revision: str | None = "8c5d1e3f7a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transcription_job",
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "transcription_job",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "transcription_job",
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "transcription_job",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "transcription_job",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE transcription_job SET idempotency_key = "
        "'transcription-' || id::text WHERE idempotency_key IS NULL"
    )
    # Jobs que estavam dentro do antigo BackgroundTasks não possuem lease e
    # jamais voltariam sozinhos após o deploy. Eles entram novamente na fila.
    op.execute(
        "UPDATE transcription_job SET status = 'queued', "
        "error_code = 'worker_interrupted', next_attempt_at = now() "
        "WHERE status = 'processing'"
    )
    op.alter_column("transcription_job", "idempotency_key", nullable=False)
    op.create_unique_constraint(
        "uq_transcription_job_idempotency_key", "transcription_job", ["idempotency_key"]
    )
    op.create_check_constraint(
        "ck_transcription_attempt_count", "transcription_job", "attempt_count >= 0"
    )
    op.create_check_constraint(
        "ck_transcription_max_attempts", "transcription_job", "max_attempts > 0"
    )
    op.create_index(
        op.f("ix_transcription_job_next_attempt_at"),
        "transcription_job",
        ["next_attempt_at"],
    )
    op.alter_column("transcription_job", "attempt_count", server_default=None)
    op.alter_column("transcription_job", "max_attempts", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_transcription_job_next_attempt_at"), table_name="transcription_job")
    op.drop_constraint("ck_transcription_max_attempts", "transcription_job", type_="check")
    op.drop_constraint("ck_transcription_attempt_count", "transcription_job", type_="check")
    op.drop_constraint("uq_transcription_job_idempotency_key", "transcription_job", type_="unique")
    op.drop_column("transcription_job", "processing_started_at")
    op.drop_column("transcription_job", "next_attempt_at")
    op.drop_column("transcription_job", "max_attempts")
    op.drop_column("transcription_job", "attempt_count")
    op.drop_column("transcription_job", "idempotency_key")
