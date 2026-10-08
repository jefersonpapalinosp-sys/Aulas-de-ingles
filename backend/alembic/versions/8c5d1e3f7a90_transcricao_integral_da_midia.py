"""transcricao integral da midia

Revision ID: 8c5d1e3f7a90
Revises: f17c0a4d8e52
Create Date: 2026-10-08 12:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8c5d1e3f7a90"
down_revision: str | None = "f17c0a4d8e52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lesson_media",
        sa.Column(
            "transcript",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("lesson_media", "transcript", server_default=None)


def downgrade() -> None:
    op.drop_column("lesson_media", "transcript")
