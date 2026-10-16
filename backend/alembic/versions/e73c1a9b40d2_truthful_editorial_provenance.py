"""40B.2c: remove datas de revisão geradas sem evidência editorial."""

import sqlalchemy as sa

from alembic import op

revision = "e73c1a9b40d2"
down_revision = "d62a0ef357b9"
branch_labels = None
depends_on = None

LEGACY_NOTE = "Conteúdo revisado contra o plano oficial e adaptado ao piloto."
UNKNOWN_NOTE = (
    "Registro legado sem nota de revisão detalhada; "
    "validação pedagógica humana permanece pendente."
)


def upgrade() -> None:
    op.alter_column(
        "lesson_version",
        "reviewed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    # O seed legado atribuía 07/10 a toda versão, inclusive a aulas cujas
    # fontes só foram acessadas dias depois. NULL preserva a verdade: data
    # desconhecida. Resultados e snapshots de alunos não são recalculados.
    op.execute(
        "UPDATE lesson_version SET reviewed_at = NULL "
        "WHERE reviewed_at = TIMESTAMPTZ '2026-10-07 00:00:00+00'"
    )
    op.execute(
        sa.text("UPDATE lesson_version SET review_note = :replacement WHERE review_note = :legacy")
        .bindparams(replacement=UNKNOWN_NOTE, legacy=LEGACY_NOTE)
    )
    op.execute(
        "UPDATE lesson_version SET published_at = NULL "
        "WHERE published_at = TIMESTAMPTZ '2026-10-07 00:00:00+00'"
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM lesson_version WHERE reviewed_at IS NULL)")
    ):
        raise RuntimeError(
            "Proveniência desconhecida não pode receber uma data inventada no downgrade."
        )
    op.alter_column(
        "lesson_version",
        "reviewed_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
