"""catalogo de cursos e unidades

Revision ID: c1d4e8f6a290
Revises: a7f3c9d2e641
Create Date: 2026-10-08 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d4e8f6a290"
down_revision: str | None = "a7f3c9d2e641"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=False),
        sa.Column("proficiency_label", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_lessons", sa.Integer(), nullable=False),
        sa.CheckConstraint("position > 0", name="ck_course_position_positive"),
        sa.CheckConstraint("total_lessons > 0", name="ck_course_total_lessons_positive"),
        sa.CheckConstraint(
            "status IN ('planned', 'published', 'archived')", name="ck_course_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("position"),
    )
    op.create_index("ix_course_slug", "course", ["slug"], unique=True)
    op.create_table(
        "course_unit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("lesson_start", sa.Integer(), nullable=False),
        sa.Column("lesson_end", sa.Integer(), nullable=False),
        sa.Column("total_lessons", sa.Integer(), nullable=False),
        sa.CheckConstraint("position > 0", name="ck_course_unit_position_positive"),
        sa.CheckConstraint("lesson_start > 0", name="ck_course_unit_lesson_start_positive"),
        sa.CheckConstraint("lesson_end >= lesson_start", name="ck_course_unit_lesson_range"),
        sa.CheckConstraint("total_lessons > 0", name="ck_course_unit_total_lessons_positive"),
        sa.CheckConstraint(
            "status IN ('planned', 'published', 'archived')", name="ck_course_unit_status"
        ),
        sa.ForeignKeyConstraint(["course_id"], ["course.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "course_id", name="uq_course_unit_id_course"),
        sa.UniqueConstraint("course_id", "slug", name="uq_course_unit_course_slug"),
        sa.UniqueConstraint("course_id", "position", name="uq_course_unit_course_position"),
    )
    op.create_index("ix_course_unit_course_id", "course_unit", ["course_id"], unique=False)

    op.execute(
        "INSERT INTO course "
        "(slug, title, level, proficiency_label, provider, source_url, position, status, "
        "total_lessons) VALUES "
        "('voa-level-1', 'Let''s Learn English — Level 1', '1', 'Iniciante', "
        "'VOA Learning English', 'https://learningenglish.voanews.com/p/5644.html', "
        "1, 'published', 52)"
    )
    op.execute(
        "INSERT INTO course_unit "
        "(course_id, slug, title, position, status, lesson_start, lesson_end, total_lessons) "
        "SELECT id, '31-40', 'Aulas 31–40', 1, 'published', 31, 40, 10 "
        "FROM course WHERE slug = 'voa-level-1'"
    )

    op.add_column("lesson", sa.Column("course_id", sa.Integer(), nullable=True))
    op.add_column("lesson", sa.Column("unit_id", sa.Integer(), nullable=True))
    op.add_column("lesson", sa.Column("slug", sa.String(length=120), nullable=True))
    op.add_column("lesson", sa.Column("position", sa.Integer(), nullable=True))
    op.add_column("lesson", sa.Column("warmup_prompt", sa.Text(), nullable=True))
    op.add_column("lesson", sa.Column("listening_focus", sa.Text(), nullable=True))

    op.execute(
        "WITH ranked AS ("
        "SELECT id, row_number() OVER (ORDER BY number, id)::integer AS position FROM lesson"
        ") UPDATE lesson AS target SET "
        "course_id = (SELECT id FROM course WHERE slug = 'voa-level-1'), "
        "unit_id = (SELECT id FROM course_unit WHERE slug = '31-40' AND course_id = "
        "(SELECT id FROM course WHERE slug = 'voa-level-1')), "
        "slug = 'lesson-' || target.number::text, "
        "position = ranked.position, "
        "warmup_prompt = CASE target.number "
        "WHEN 31 THEN 'Como você compararia duas formas de transporte?' "
        "WHEN 32 THEN 'Como você pediria uma informação e responderia com entusiasmo?' "
        "WHEN 33 THEN 'Como você explicaria, em ordem, as regras de um esporte?' "
        "WHEN 34 THEN 'Como você falaria sobre um plano futuro que ainda não é certo?' "
        "WHEN 35 THEN 'Como você pediria quantidades e embalagens em uma lista de compras?' "
        "WHEN 36 THEN 'Como você diria onde estão os ingredientes e se ofereceria para ajudar?' "
        "WHEN 37 THEN 'Como você concordaria ou discordaria de uma opinião com educação?' "
        "WHEN 38 THEN 'Como você descreveria seu melhor amigo usando superlativos?' "
        "WHEN 39 THEN 'Como você explicaria que um produto não cumpriu o que prometeu?' "
        "WHEN 40 THEN 'Como você pediria para alguém falar mais alto ou andar mais devagar?' "
        "ELSE 'O que você já consegue dizer sobre o tema desta aula?' END, "
        "listening_focus = CASE target.number "
        "WHEN 31 THEN 'os transportes comparados e o conselho final' "
        "WHEN 32 THEN 'quem recebe cada pergunta ou resposta e as interjeições' "
        "WHEN 33 THEN 'os marcadores de sequência e quem realiza cada ação no beisebol' "
        "WHEN 34 THEN 'a diferença de certeza entre *might* e *will*' "
        "WHEN 35 THEN 'as embalagens, quantidades e a lista de compras errada' "
        "WHEN 36 THEN 'as preposições de lugar e as decisões com *I’ll*' "
        "WHEN 37 THEN 'os possessivos e as frases usadas para concordar ou discordar' "
        "WHEN 38 THEN 'os superlativos empregados para descrever cada amigo' "
        "WHEN 39 THEN 'os prefixos negativos e as pistas que revelam o problema do produto' "
        "WHEN 40 THEN 'os advérbios que mudam a maneira e o momento de cada ação' "
        "ELSE 'as palavras-chave e o objetivo comunicativo da aula' END "
        "FROM ranked WHERE target.id = ranked.id"
    )

    for column in (
        "course_id",
        "unit_id",
        "slug",
        "position",
        "warmup_prompt",
        "listening_focus",
    ):
        op.alter_column("lesson", column, nullable=False)

    op.drop_index("ix_lesson_number", table_name="lesson")
    op.create_index("ix_lesson_number", "lesson", ["number"], unique=False)
    op.create_index("ix_lesson_course_id", "lesson", ["course_id"], unique=False)
    op.create_index("ix_lesson_unit_id", "lesson", ["unit_id"], unique=False)
    op.create_foreign_key(
        "fk_lesson_course", "lesson", "course", ["course_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_lesson_unit_course",
        "lesson",
        "course_unit",
        ["unit_id", "course_id"],
        ["id", "course_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_lesson_course_number", "lesson", ["course_id", "number"])
    op.create_unique_constraint("uq_lesson_course_slug", "lesson", ["course_id", "slug"])
    op.create_unique_constraint("uq_lesson_unit_position", "lesson", ["unit_id", "position"])
    op.create_check_constraint("ck_lesson_number_positive", "lesson", "number > 0")
    op.create_check_constraint("ck_lesson_position_positive", "lesson", "position > 0")


def downgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text("SELECT 1 FROM lesson GROUP BY number HAVING count(*) > 1 LIMIT 1")
    ).scalar_one_or_none()
    if duplicate is not None:
        raise RuntimeError(
            "Downgrade bloqueado: há números de aula repetidos entre cursos; "
            "remova a ambiguidade sem apagar histórico antes de restaurar a unicidade global."
        )

    op.drop_constraint("ck_lesson_position_positive", "lesson", type_="check")
    op.drop_constraint("ck_lesson_number_positive", "lesson", type_="check")
    op.drop_constraint("uq_lesson_unit_position", "lesson", type_="unique")
    op.drop_constraint("uq_lesson_course_slug", "lesson", type_="unique")
    op.drop_constraint("uq_lesson_course_number", "lesson", type_="unique")
    op.drop_constraint("fk_lesson_unit_course", "lesson", type_="foreignkey")
    op.drop_constraint("fk_lesson_course", "lesson", type_="foreignkey")
    op.drop_index("ix_lesson_unit_id", table_name="lesson")
    op.drop_index("ix_lesson_course_id", table_name="lesson")
    op.drop_index("ix_lesson_number", table_name="lesson")
    op.drop_column("lesson", "listening_focus")
    op.drop_column("lesson", "warmup_prompt")
    op.drop_column("lesson", "position")
    op.drop_column("lesson", "slug")
    op.drop_column("lesson", "unit_id")
    op.drop_column("lesson", "course_id")
    op.create_index("ix_lesson_number", "lesson", ["number"], unique=True)
    op.drop_index("ix_course_unit_course_id", table_name="course_unit")
    op.drop_table("course_unit")
    op.drop_index("ix_course_slug", table_name="course")
    op.drop_table("course")
