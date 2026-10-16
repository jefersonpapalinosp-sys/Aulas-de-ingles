"""alinha a posicao canonica da unidade 31-40 do Level 1

Revision ID: a42c7d1e9f20
Revises: f40c2d9a1b73
Create Date: 2026-10-16

A primeira migration do catalogo criou a unidade 31-40 na posicao 1 porque ela
era, naquele momento, a unica unidade persistida. O catalogo atual inclui as
unidades 1-5 ate 26-30 antes dela, portanto um banco criado do zero precisa
nascer com a posicao 7 para que o seed insert-only nao interprete a diferenca
como uma edicao editorial proibida.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a42c7d1e9f20"
down_revision: str | None = "f40c2d9a1b73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE course_unit AS target
               SET position = 7
              FROM course
             WHERE target.course_id = course.id
               AND course.slug = 'voa-level-1'
               AND target.slug = '31-40'
               AND target.position = 1
               AND NOT EXISTS (
                   SELECT 1
                     FROM course_unit AS occupied
                    WHERE occupied.course_id = target.course_id
                      AND occupied.position = 7
                      AND occupied.id <> target.id
               )
            """
        )
    )


def downgrade() -> None:
    # Reverte apenas quando a posicao historica 1 continua livre. Em bancos ja
    # semeados ela pertence a unidade 1-5 e deslocar dados publicados seria
    # incorreto; nesse caso a posicao canonica 7 e preservada.
    op.execute(
        sa.text(
            """
            UPDATE course_unit AS target
               SET position = 1
              FROM course
             WHERE target.course_id = course.id
               AND course.slug = 'voa-level-1'
               AND target.slug = '31-40'
               AND target.position = 7
               AND NOT EXISTS (
                   SELECT 1
                     FROM course_unit AS occupied
                    WHERE occupied.course_id = target.course_id
                      AND occupied.position = 1
                      AND occupied.id <> target.id
               )
            """
        )
    )
