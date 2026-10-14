"""Versiona novos feedbacks sem recalcular evidências antigas.

Revision ID: c95f3d8ba042
Revises: b84e2c7a9d31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c95f3d8ba042"
down_revision: str | None = "b84e2c7a9d31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "writing_feedback",
        sa.Column("algorithm_version", sa.String(50), nullable=False, server_default="legacy-v1"),
    )
    op.add_column("writing_feedback", sa.Column("rubric_version", sa.String(71), nullable=True))
    op.add_column(
        "writing_feedback", sa.Column("rubric_snapshot", postgresql.JSONB(), nullable=True)
    )
    op.create_check_constraint(
        "ck_writing_feedback_v2_snapshot",
        "writing_feedback",
        "algorithm_version != 'writing-rules-v2' OR (rubric_version IS NOT NULL AND rubric_snapshot IS NOT NULL)",
    )


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM writing_feedback WHERE algorithm_version != 'legacy-v1' "
                "OR rubric_snapshot IS NOT NULL OR rubric_version IS NOT NULL LIMIT 1"
            )
        )
        .first()
    ):
        raise RuntimeError(
            "Downgrade bloqueado: existem feedbacks versionados; preserve seu histórico."
        )
    op.drop_constraint("ck_writing_feedback_v2_snapshot", "writing_feedback", type_="check")
    op.drop_column("writing_feedback", "rubric_snapshot")
    op.drop_column("writing_feedback", "rubric_version")
    op.drop_column("writing_feedback", "algorithm_version")
