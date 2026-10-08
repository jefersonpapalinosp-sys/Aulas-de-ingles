"""revisao multimodal adaptativa

Revision ID: d79a1c35b681
Revises: c68f9b24a570
Create Date: 2026-10-08 03:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d79a1c35b681"
down_revision: str | None = "c68f9b24a570"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("vocab_item_id", sa.Integer(), nullable=True),
        sa.Column("legacy_card_id", sa.Integer(), nullable=True),
        sa.Column("item_type", sa.String(length=30), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("skill", sa.String(length=40), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("prompt_note", sa.String(length=200), nullable=True),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("origin_reason", sa.String(length=300), nullable=False),
        sa.Column("media_url", sa.String(length=1000), nullable=True),
        sa.Column("cue_start_seconds", sa.Float(), nullable=True),
        sa.Column("cue_end_seconds", sa.Float(), nullable=True),
        sa.Column("estimated_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ease_factor", sa.Float(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("estimated_seconds > 0", name="ck_review_item_duration_positive"),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="ck_review_item_status"),
        sa.CheckConstraint(
            "item_type IN ('vocabulary', 'grammar_error', 'phrase', 'listening', "
            "'writing_prompt', 'speaking_prompt')",
            name="ck_review_item_type",
        ),
        sa.ForeignKeyConstraint(["legacy_card_id"], ["review_card.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lesson.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vocab_item_id"], ["vocab_item.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legacy_card_id", name="uq_review_item_legacy_card"),
        sa.UniqueConstraint("user_id", "source_key", name="uq_review_item_user_source"),
    )
    op.create_index(op.f("ix_review_item_due_at"), "review_item", ["due_at"])
    op.create_index(op.f("ix_review_item_item_type"), "review_item", ["item_type"])
    op.create_index(op.f("ix_review_item_lesson_id"), "review_item", ["lesson_id"])
    op.create_index(op.f("ix_review_item_skill"), "review_item", ["skill"])
    op.create_index(op.f("ix_review_item_status"), "review_item", ["status"])
    op.create_index(op.f("ix_review_item_user_id"), "review_item", ["user_id"])
    op.create_index(op.f("ix_review_item_vocab_item_id"), "review_item", ["vocab_item_id"])

    # Copia o deck sem recalcular nada: IDs e todo o estado SM-2 permanecem iguais.
    op.execute(
        """
        INSERT INTO review_item (
            id, user_id, lesson_id, vocab_item_id, legacy_card_id,
            item_type, source_type, source_id, source_key, skill,
            prompt, prompt_note, answer, context, origin_reason,
            estimated_seconds, status, ease_factor, interval_days,
            repetitions, lapses, due_at, last_reviewed_at, created_at
        )
        SELECT rc.id, rc.user_id, v.lesson_id, v.id, rc.id,
               'vocabulary', 'vocab_item', v.id, 'vocab:' || v.id, 'vocabulary',
               v.term, v.ipa, v.translation_pt, v.example_en,
               'Vocabulário incluído no seu deck de estudo.',
               45, 'active', rc.ease_factor, rc.interval_days,
               rc.repetitions, rc.lapses, rc.due_at, rc.last_reviewed_at, rc.created_at
          FROM review_card rc
          JOIN vocab_item v ON v.id = rc.vocab_item_id
        """
    )
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('review_item', 'id'),
            COALESCE((SELECT MAX(id) FROM review_item), 1),
            EXISTS (SELECT 1 FROM review_item)
        )
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_review_item_vocab_item_id"), table_name="review_item")
    op.drop_index(op.f("ix_review_item_user_id"), table_name="review_item")
    op.drop_index(op.f("ix_review_item_status"), table_name="review_item")
    op.drop_index(op.f("ix_review_item_skill"), table_name="review_item")
    op.drop_index(op.f("ix_review_item_lesson_id"), table_name="review_item")
    op.drop_index(op.f("ix_review_item_item_type"), table_name="review_item")
    op.drop_index(op.f("ix_review_item_due_at"), table_name="review_item")
    op.drop_table("review_item")
