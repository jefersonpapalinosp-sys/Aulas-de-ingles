"""40B.2e: listening links use IDs; legacy positions are only compatibility data."""

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CourseReview, Exercise, Lesson, LessonMedia


async def test_migration_backfilled_every_legacy_listening_link(session: AsyncSession) -> None:
    media = list(
        (
            await session.execute(
                select(LessonMedia).where(LessonMedia.listening_exercise_position.is_not(None))
            )
        ).scalars()
    )
    reviews = list(
        (
            await session.execute(
                select(CourseReview).where(CourseReview.listening_media_position.is_not(None))
            )
        ).scalars()
    )
    assert media and reviews
    assert all(item.listening_exercise_id is not None for item in media)
    assert all(item.listening_course_id is not None for item in reviews)
    assert all(item.listening_lesson_id is not None for item in reviews)
    assert all(item.listening_media_id is not None for item in reviews)


async def test_links_survive_reorder_and_cross_lesson_links_are_rejected(
    session: AsyncSession,
) -> None:
    media = (
        await session.execute(
            select(LessonMedia)
            .where(LessonMedia.listening_exercise_id.is_not(None))
            .order_by(LessonMedia.id)
            .limit(1)
        )
    ).scalar_one()
    target = await session.get(Exercise, media.listening_exercise_id)
    assert target is not None
    other = (
        await session.execute(
            select(Exercise)
            .where(Exercise.lesson_id != media.lesson_id)
            .order_by(Exercise.id)
            .limit(1)
        )
    ).scalar_one()

    savepoint = await session.begin_nested()
    try:
        await session.execute(
            update(Exercise).where(Exercise.id == target.id).values(position=99_999)
        )
        assert (
            await session.scalar(
                select(LessonMedia.listening_exercise_id).where(LessonMedia.id == media.id)
            )
            == target.id
        )
        assert media.listening_exercise_position != 99_999

        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    update(LessonMedia)
                    .where(LessonMedia.id == media.id)
                    .values(listening_exercise_id=other.id)
                )
    finally:
        await savepoint.rollback()
        await session.rollback()


async def test_checkpoint_link_survives_media_reorder_and_cannot_cross_course(
    session: AsyncSession,
) -> None:
    review = (
        await session.execute(
            select(CourseReview)
            .where(CourseReview.listening_media_id.is_not(None))
            .order_by(CourseReview.id)
            .limit(1)
        )
    ).scalar_one()
    target = await session.get(LessonMedia, review.listening_media_id)
    assert target is not None
    other_lesson, other_media = (
        await session.execute(
            select(Lesson, LessonMedia)
            .join(LessonMedia, LessonMedia.lesson_id == Lesson.id)
            .where(Lesson.course_id != review.listening_course_id)
            .order_by(Lesson.id, LessonMedia.id)
            .limit(1)
        )
    ).one()

    savepoint = await session.begin_nested()
    try:
        await session.execute(
            update(LessonMedia).where(LessonMedia.id == target.id).values(position=99_999)
        )
        assert (
            await session.scalar(
                select(CourseReview.listening_media_id).where(CourseReview.id == review.id)
            )
            == target.id
        )
        assert review.listening_media_position != 99_999

        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    update(CourseReview)
                    .where(CourseReview.id == review.id)
                    .values(
                        listening_course_id=other_lesson.course_id,
                        listening_lesson_id=other_lesson.id,
                        listening_media_id=other_media.id,
                    )
                )
    finally:
        await savepoint.rollback()
        await session.rollback()
