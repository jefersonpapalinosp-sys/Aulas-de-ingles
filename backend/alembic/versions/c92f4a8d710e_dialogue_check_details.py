"""FE-47: recorte histórico dos critérios de cada turno, sem reconstruir legados.

Revision ID: c92f4a8d710e
Revises: a18d7e4c2b91
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c92f4a8d710e"
down_revision: str | None = "a18d7e4c2b91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dialogue_turn",
        sa.Column("check_details", postgresql.JSONB(none_as_null=True), nullable=True),
    )
    op.execute("""DO $$ BEGIN
        IF current_user = 'aulas_owner'
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_worker') THEN
            GRANT UPDATE (check_details) ON dialogue_turn TO aulas_worker;
        END IF;
    END $$""")


def downgrade() -> None:
    count = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM dialogue_turn WHERE check_details IS NOT NULL")
    )
    if count:
        raise RuntimeError(f"downgrade bloqueado: {count} turnos com detalhes históricos")
    op.drop_column("dialogue_turn", "check_details")
