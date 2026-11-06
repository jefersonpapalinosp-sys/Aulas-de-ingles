"""Sprint 56: recibos de atividade/revisão e FK em bigint, sem truncar no retorno."""

import sqlalchemy as sa
from alembic import op

revision = "c56b1c8d9006"
down_revision = "b56b1c8d9005"
branch_labels = None
depends_on = None

TABLES = ("review_event", "study_activity_event", "study_active_interval")


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "id", existing_type=sa.Integer(), type_=sa.BigInteger())
        op.execute(f"ALTER SEQUENCE {table}_id_seq AS bigint")
    op.alter_column(
        "study_active_interval", "event_id", existing_type=sa.Integer(), type_=sa.BigInteger()
    )


def downgrade() -> None:
    # Exclui concorrência entre a contagem, a conversão e o ajuste da sequência.
    op.execute(
        "LOCK TABLE review_event, study_activity_event, study_active_interval IN ACCESS EXCLUSIVE MODE"
    )
    for table in TABLES:
        overflow = (
            op.get_bind()
            .execute(
                sa.text(
                    f"SELECT EXISTS(SELECT 1 FROM {table} WHERE id NOT BETWEEN -2147483648 AND 2147483647) "
                    f"OR (SELECT last_value NOT BETWEEN -2147483648 AND 2147483647 FROM {table}_id_seq)"
                )
            )
            .scalar_one()
        )
        if overflow:
            raise RuntimeError(
                "Downgrade recusado: eventos/sequência excedem integer; preserve os dados."
            )
    for table in TABLES:
        op.alter_column(table, "id", existing_type=sa.BigInteger(), type_=sa.Integer())
        op.execute(f"ALTER SEQUENCE {table}_id_seq AS integer")
    op.alter_column(
        "study_active_interval", "event_id", existing_type=sa.BigInteger(), type_=sa.Integer()
    )
