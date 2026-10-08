"""checkpoint invariants

Revision ID: a73c9e1d5b20
Revises: f62a8d4c1e90
Create Date: 2026-10-08 23:30:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a73c9e1d5b20"
down_revision: str | None = "f62a8d4c1e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_course_review_lesson_positive",
        "course_review",
        "review_lesson_number > 0",
    )
    op.create_check_constraint(
        "ck_course_review_listening_lesson_positive",
        "course_review",
        "listening_lesson_number IS NULL OR listening_lesson_number > 0",
    )
    op.create_check_constraint(
        "ck_course_review_listening_position_nonnegative",
        "course_review",
        "listening_media_position IS NULL OR listening_media_position >= 0",
    )
    op.create_check_constraint(
        "ck_course_review_listening_pair",
        "course_review",
        "(listening_lesson_number IS NULL) = (listening_media_position IS NULL)",
    )
    op.create_check_constraint(
        "ck_course_review_question_answers_nonempty",
        "course_review_question",
        "jsonb_array_length(accepted_answers) > 0",
    )
    op.create_check_constraint(
        "ck_course_review_question_lessons_nonempty",
        "course_review_question",
        "jsonb_array_length(lesson_numbers) > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_course_review_question_lessons_nonempty",
        "course_review_question",
        type_="check",
    )
    op.drop_constraint(
        "ck_course_review_question_answers_nonempty",
        "course_review_question",
        type_="check",
    )
    op.drop_constraint(
        "ck_course_review_listening_pair", "course_review", type_="check"
    )
    op.drop_constraint(
        "ck_course_review_listening_position_nonnegative",
        "course_review",
        type_="check",
    )
    op.drop_constraint(
        "ck_course_review_listening_lesson_positive",
        "course_review",
        type_="check",
    )
    op.drop_constraint(
        "ck_course_review_lesson_positive", "course_review", type_="check"
    )
