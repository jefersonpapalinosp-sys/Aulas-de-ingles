"""classification exercises

Revision ID: b84e2c7a9d31
Revises: a73c9e1d5b20
Create Date: 2026-10-09 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b84e2c7a9d31"
down_revision: str | None = "a73c9e1d5b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exercise",
        sa.Column(
            "classification_items",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "exercise",
        sa.Column(
            "classification_categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    # `activity_type` já era texto livre. Uma implantação que carregou o seed
    # novo antes da migration pode ter registros classification sem as colunas
    # estruturadas; degrade-os temporariamente e deixe o seed idempotente
    # recompô-los depois do upgrade.
    op.execute(
        "UPDATE exercise SET activity_type = 'gap_fill' WHERE activity_type = 'classification'"
    )
    op.create_check_constraint(
        "ck_exercise_classification_contract",
        "exercise",
        "activity_type != 'classification' OR "
        "(classification_items IS NOT NULL AND "
        "jsonb_typeof(classification_items) = 'array' AND "
        "jsonb_array_length(classification_items) > 0 AND "
        "classification_categories IS NOT NULL AND "
        "jsonb_typeof(classification_categories) = 'array' AND "
        "jsonb_array_length(classification_categories) >= 2)",
    )
    op.alter_column(
        "exercise_answer",
        "value",
        existing_type=sa.String(length=200),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "exercise_attempt",
        "answer",
        existing_type=sa.String(length=200),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Nenhum UPDATE/DDL antes da guarda: jamais trunca respostas silenciosamente.
    op.execute("LOCK TABLE exercise_attempt, exercise_answer IN SHARE ROW EXCLUSIVE MODE")
    count = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM exercise_attempt WHERE length(answer) > 200) + "
                "(SELECT count(*) FROM exercise_answer WHERE length(value) > 200)"
            )
        )
        .scalar_one()
    )
    if count:
        raise RuntimeError(f"Downgrade recusado: {count} respostas excedem 200 caracteres.")
    # A versão anterior não sabe renderizar nem validar classification. Ao
    # voltar, degrade o tipo para uma resposta textual e remova filtros de
    # sessões ativas; o próximo seed restaura o contrato estruturado.
    op.execute(
        "UPDATE practice_session SET activity_type = NULL WHERE activity_type = 'classification'"
    )
    op.execute(
        "UPDATE exercise SET activity_type = 'gap_fill' WHERE activity_type = 'classification'"
    )
    op.alter_column(
        "exercise_attempt",
        "answer",
        existing_type=sa.Text(),
        type_=sa.String(length=200),
        existing_nullable=False,
    )
    op.alter_column(
        "exercise_answer",
        "value",
        existing_type=sa.Text(),
        type_=sa.String(length=200),
        existing_nullable=False,
    )
    op.drop_constraint("ck_exercise_classification_contract", "exercise", type_="check")
    op.drop_column("exercise", "classification_categories")
    op.drop_column("exercise", "classification_items")
