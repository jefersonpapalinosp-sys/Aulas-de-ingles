"""40B.2e: replace positional cross-entity lookups with stable foreign keys.

Revision ID: a06f2ce1487b
Revises: f84d1b6c2a90
Create Date: 2026-10-15 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a06f2ce1487b"
down_revision: str | None = "f84d1b6c2a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _assert_no_unresolved_links() -> None:
    connection = op.get_bind()
    missing_media = connection.scalar(
        sa.text(
            """SELECT count(*) FROM lesson_media
               WHERE listening_exercise_position IS NOT NULL
                 AND listening_exercise_id IS NULL"""
        )
    )
    missing_reviews = connection.scalar(
        sa.text(
            """SELECT count(*) FROM course_review
               WHERE listening_media_position IS NOT NULL
                 AND (listening_course_id IS NULL OR listening_lesson_id IS NULL
                      OR listening_media_id IS NULL)"""
        )
    )
    if missing_media or missing_reviews:
        raise RuntimeError(
            "Referências posicionais ambíguas ou ausentes; corrija o catálogo antes da migration."
        )


def upgrade() -> None:
    op.add_column("lesson_media", sa.Column("listening_exercise_id", sa.Integer(), nullable=True))
    op.add_column("course_review", sa.Column("listening_course_id", sa.Integer(), nullable=True))
    op.add_column("course_review", sa.Column("listening_lesson_id", sa.Integer(), nullable=True))
    op.add_column("course_review", sa.Column("listening_media_id", sa.Integer(), nullable=True))

    op.execute(
        """UPDATE lesson_media AS media
           SET listening_exercise_id = exercise.id
           FROM exercise
           WHERE media.listening_exercise_position IS NOT NULL
             AND exercise.lesson_id = media.lesson_id
             AND exercise.position = media.listening_exercise_position"""
    )
    op.execute(
        """UPDATE course_review AS review
           SET listening_course_id = unit.course_id,
               listening_lesson_id = lesson.id,
               listening_media_id = media.id
           FROM course_unit AS unit
           JOIN lesson ON lesson.course_id = unit.course_id
           JOIN lesson_media AS media ON media.lesson_id = lesson.id
           WHERE review.listening_media_position IS NOT NULL
             AND unit.id = review.unit_id
             AND lesson.number = review.listening_lesson_number
             AND media.position = review.listening_media_position"""
    )
    _assert_no_unresolved_links()

    op.create_unique_constraint("uq_exercise_lesson_id", "exercise", ["lesson_id", "id"])
    op.create_unique_constraint(
        "uq_lesson_media_lesson_id", "lesson_media", ["lesson_id", "id"]
    )
    op.create_unique_constraint("uq_lesson_id_course", "lesson", ["id", "course_id"])

    op.create_foreign_key(
        "fk_lesson_media_listening_exercise_lesson",
        "lesson_media",
        "exercise",
        ["lesson_id", "listening_exercise_id"],
        ["lesson_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_course_review_unit_course",
        "course_review",
        "course_unit",
        ["unit_id", "listening_course_id"],
        ["id", "course_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_course_review_listening_lesson_course",
        "course_review",
        "lesson",
        ["listening_lesson_id", "listening_course_id"],
        ["id", "course_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_course_review_listening_media_lesson",
        "course_review",
        "lesson_media",
        ["listening_lesson_id", "listening_media_id"],
        ["lesson_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_lesson_media_listening_exercise_id",
        "lesson_media",
        ["listening_exercise_id"],
    )
    op.create_index(
        "ix_course_review_listening_course_id",
        "course_review",
        ["listening_course_id"],
    )
    op.create_index(
        "ix_course_review_listening_lesson_id",
        "course_review",
        ["listening_lesson_id"],
    )
    op.create_index(
        "ix_course_review_listening_media_id",
        "course_review",
        ["listening_media_id"],
    )

    op.drop_constraint("ck_course_review_listening_pair", "course_review", type_="check")
    op.create_check_constraint(
        "ck_course_review_listening_pair",
        "course_review",
        "(listening_lesson_number IS NULL) = (listening_media_position IS NULL) AND "
        "(listening_media_position IS NULL) = (listening_course_id IS NULL) AND "
        "(listening_course_id IS NULL) = (listening_lesson_id IS NULL) AND "
        "(listening_lesson_id IS NULL) = (listening_media_id IS NULL)",
    )


def downgrade() -> None:
    connection = op.get_bind()
    changed = connection.scalar(
        sa.text(
            """SELECT EXISTS (
                 SELECT 1 FROM lesson_media media
                 JOIN exercise ON exercise.id = media.listening_exercise_id
                 WHERE exercise.position IS DISTINCT FROM media.listening_exercise_position
                 UNION ALL
                 SELECT 1 FROM course_review review
                 JOIN lesson ON lesson.id = review.listening_lesson_id
                 JOIN lesson_media media ON media.id = review.listening_media_id
                 WHERE lesson.number IS DISTINCT FROM review.listening_lesson_number
                    OR media.position IS DISTINCT FROM review.listening_media_position
               )"""
        )
    )
    if changed:
        raise RuntimeError(
            "Downgrade recusado: posições mudaram e não representam mais os vínculos estáveis."
        )

    op.drop_constraint("ck_course_review_listening_pair", "course_review", type_="check")
    op.create_check_constraint(
        "ck_course_review_listening_pair",
        "course_review",
        "(listening_lesson_number IS NULL) = (listening_media_position IS NULL)",
    )
    op.drop_index("ix_course_review_listening_media_id", table_name="course_review")
    op.drop_index("ix_course_review_listening_lesson_id", table_name="course_review")
    op.drop_index("ix_course_review_listening_course_id", table_name="course_review")
    op.drop_index("ix_lesson_media_listening_exercise_id", table_name="lesson_media")
    op.drop_constraint(
        "fk_course_review_listening_media_lesson", "course_review", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_course_review_listening_lesson_course", "course_review", type_="foreignkey"
    )
    op.drop_constraint("fk_course_review_unit_course", "course_review", type_="foreignkey")
    op.drop_constraint(
        "fk_lesson_media_listening_exercise_lesson", "lesson_media", type_="foreignkey"
    )
    op.drop_constraint("uq_lesson_id_course", "lesson", type_="unique")
    op.drop_constraint("uq_lesson_media_lesson_id", "lesson_media", type_="unique")
    op.drop_constraint("uq_exercise_lesson_id", "exercise", type_="unique")
    op.drop_column("course_review", "listening_media_id")
    op.drop_column("course_review", "listening_lesson_id")
    op.drop_column("course_review", "listening_course_id")
    op.drop_column("lesson_media", "listening_exercise_id")
