"""politica de licenca de midia

Revision ID: a7f3c9d2e641
Revises: 9d6e2f4a8b31
Create Date: 2026-10-08 16:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7f3c9d2e641"
down_revision: str | None = "9d6e2f4a8b31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lesson_media",
        sa.Column(
            "license_status", sa.String(length=30), server_default="review_required", nullable=False
        ),
    )
    op.add_column("lesson_media", sa.Column("license_url", sa.String(length=1000), nullable=True))
    op.add_column(
        "lesson_media",
        sa.Column(
            "license_note",
            sa.String(length=500),
            server_default="Licença ainda não revisada.",
            nullable=False,
        ),
    )
    op.add_column(
        "lesson_media",
        sa.Column(
            "attribution", sa.String(length=200), server_default="Fonte externa", nullable=False
        ),
    )
    op.add_column(
        "lesson_media",
        sa.Column(
            "offline_policy", sa.String(length=20), server_default="network_only", nullable=False
        ),
    )
    op.add_column("lesson_media", sa.Column("license_reviewed_at", sa.Date(), nullable=True))
    op.execute(
        "UPDATE lesson_media SET "
        "license_status = 'public_domain', "
        "license_url = 'https://learningenglish.voanews.com/p/6021.html', "
        "license_note = 'Produção exclusiva da VOA em domínio público; materiais de terceiros "
        "não estão incluídos.', "
        "attribution = 'Voice of America (VOA Learning English)', "
        "offline_policy = 'network_only', "
        "license_reviewed_at = DATE '2026-10-08' "
        "WHERE source_url LIKE 'https://voa-audio.voanews.eu/%'"
    )
    op.create_check_constraint(
        "ck_media_license_status",
        "lesson_media",
        "license_status IN ('public_domain', 'permission_granted', 'restricted', "
        "'review_required')",
    )
    op.create_check_constraint(
        "ck_media_offline_policy",
        "lesson_media",
        "offline_policy IN ('network_only', 'cache_allowed')",
    )
    op.create_check_constraint(
        "ck_media_offline_requires_license",
        "lesson_media",
        "offline_policy != 'cache_allowed' OR "
        "license_status IN ('public_domain', 'permission_granted')",
    )
    for column in ["license_status", "license_note", "attribution", "offline_policy"]:
        op.alter_column("lesson_media", column, server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_media_offline_requires_license", "lesson_media", type_="check")
    op.drop_constraint("ck_media_offline_policy", "lesson_media", type_="check")
    op.drop_constraint("ck_media_license_status", "lesson_media", type_="check")
    op.drop_column("lesson_media", "license_reviewed_at")
    op.drop_column("lesson_media", "offline_policy")
    op.drop_column("lesson_media", "attribution")
    op.drop_column("lesson_media", "license_note")
    op.drop_column("lesson_media", "license_url")
    op.drop_column("lesson_media", "license_status")
