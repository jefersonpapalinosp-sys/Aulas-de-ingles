"""cascade da sessao fonte

Revision ID: e5f8b2c9d431
Revises: d4e7a1b8c320
Create Date: 2026-10-08 23:30:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e5f8b2c9d431"
down_revision: str | None = "d4e7a1b8c320"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "practice_session_source_session_id_fkey",
        "practice_session",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "practice_session_source_session_id_fkey",
        "practice_session",
        "practice_session",
        ["source_session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Estas invariantes foram definidas depois que a revisão d4 já havia sido
    # aplicada no ambiente de desenvolvimento. Mantê-las nesta revisão
    # incremental faz bancos existentes e instalações novas convergirem para
    # exatamente o mesmo schema.
    op.create_check_constraint(
        "ck_practice_session_source_by_mode",
        "practice_session",
        "(mode = 'mistakes' AND source_session_id IS NOT NULL) OR "
        "(mode != 'mistakes' AND source_session_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_practice_session_position_in_range",
        "practice_session",
        "current_position < total_items",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_practice_session_position_in_range",
        "practice_session",
        type_="check",
    )
    op.drop_constraint(
        "ck_practice_session_source_by_mode",
        "practice_session",
        type_="check",
    )
    op.drop_constraint(
        "practice_session_source_session_id_fkey",
        "practice_session",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "practice_session_source_session_id_fkey",
        "practice_session",
        "practice_session",
        ["source_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
