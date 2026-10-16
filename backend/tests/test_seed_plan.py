"""40B.1: only the guarded disposable PostgreSQL; never DEV/study data."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, insert, select, text, update
from sqlalchemy.exc import DBAPIError

from app.db import seed, seed_plan
from app.db.models import (
    Course,
    CourseReview,
    CourseUnit,
    Exercise,
    ExerciseAttempt,
    Lesson,
    LessonVersion,
    ReviewCardLegacy,
    SpeakingAttempt,
    User,
    WritingDraft,
    WritingRevision,
)
from app.db.seed_plan import SPECS, SeedBlocked, apply_graph, compare_graphs, read_graph, seed_graph
from app.db.session import get_engine, get_sessionmaker


def package():
    return seed.load_course_seed(), seed.load_seed()


async def editorial_rows(session):
    return {
        spec.name: [
            dict(row)
            for row in (
                await session.execute(select(spec.table).order_by(spec.table.c.id))
            ).mappings()
        ]
        for spec in SPECS
    }


async def sequences(session):
    return list(
        (
            await session.execute(
                text(
                    "SELECT sequencename, last_value FROM pg_sequences "
                    "WHERE schemaname = current_schema() ORDER BY sequencename"
                )
            )
        ).all()
    )


async def test_preview_is_read_only_bounded_and_does_not_advance_sequences(session):
    before = await editorial_rows(session)
    counters = await sequences(session)
    await session.rollback()
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", observe)
    try:
        report = await seed.preview_seed(session)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert report["allowed"] and report["dry_run"]
    assert report["changes"] == []
    assert report["counts"]["unchanged"] > 6000
    assert all(sql.lstrip().split()[0] in {"SELECT", "SET"} for sql in statements)
    assert any("REPEATABLE READ, READ ONLY" in sql for sql in statements)
    assert not any("app_user" in sql or "writing_draft" in sql for sql in statements)
    assert await editorial_rows(session) == before
    assert await sequences(session) == counters


async def test_identical_apply_does_not_recreate_descriptive_ids_or_change_dates(session):
    before = await editorial_rows(session)
    counters = await sequences(session)
    assert await seed.seed_lessons(session) == 82
    assert await editorial_rows(session) == before
    assert await sequences(session) == counters


@pytest.mark.parametrize("name", [spec.name for spec in SPECS])
async def test_every_existing_editorial_table_is_protected_even_without_users(session, name):
    _, wanted = seed.load_seed_graph()
    key = next(iter(wanted[name]))
    del wanted[name][key]
    before = await editorial_rows(session)
    with pytest.raises(SeedBlocked) as blocked:
        await apply_graph(session, wanted)
    assert any(
        change["table"] == name and change["operation"] == "omitted"
        for change in blocked.value.report["changes"]
    )
    assert await editorial_rows(session) == before


@pytest.mark.parametrize("path", ["exercise", "answer", "cue", "rubric", "version", "checkpoint"])
async def test_semantic_changes_and_version_bumps_require_immutable_history(session, path):
    courses, lessons = package()
    lesson = lessons[0]
    if path == "exercise":
        lesson["exercises"][0]["prompt"] += " Changed."
    elif path == "answer":
        lesson["exercises"][0]["answers"][0] = "different answer"
    elif path == "cue":
        lesson["media"][0]["cues"][0]["text_en"] += " Changed."
    elif path == "rubric":
        lesson["writing_prompts"][0]["min_words"] += 1
    elif path == "version":
        lesson["content_version"] = int(lesson.get("content_version", 1)) + 1
    else:
        review = next(
            unit["review"] for course in courses for unit in course["units"] if unit.get("review")
        )
        review["content_version"] += 1
        review["questions"][0]["prompt"] += " Changed."
    with pytest.raises(SeedBlocked):
        await apply_graph(session, seed_graph(courses, lessons))


async def test_addition_to_existing_lesson_is_blocked_not_silently_skipped(session):
    courses, lessons = package()
    lessons[0]["goals"].append("New editorial goal")
    with pytest.raises(SeedBlocked) as blocked:
        await apply_graph(session, seed_graph(courses, lessons))
    assert blocked.value.report["counts"]["create"] == 1
    assert blocked.value.report["counts"]["blocked"] == 1


@pytest.mark.parametrize("part", ["course", "unit", "lesson", "prompt", "cue", "position"])
def test_duplicate_editorial_identities_rejected_before_database(part):
    courses, lessons = package()
    if part == "course":
        courses.append(deepcopy(courses[0]))
    elif part == "unit":
        courses[0]["units"].append(deepcopy(courses[0]["units"][0]))
    elif part == "lesson":
        lessons.append(deepcopy(lessons[0]))
    elif part == "prompt":
        lessons[0]["writing_prompts"] *= 2
    elif part == "cue":
        lessons[0]["media"][0]["cues"] *= 2
    else:
        courses[1]["position"] = courses[0]["position"]
    with pytest.raises(ValueError, match="duplicada"):
        seed_graph(courses, lessons)


def test_listening_links_keep_identity_when_display_positions_change():
    courses, lessons = package()

    first_lesson = lessons[0]
    audio = first_lesson["media"][0]
    exercise = next(
        item
        for item in first_lesson["exercises"]
        if item["position"] == audio["listening_exercise_position"]
    )
    before = seed_graph(courses, lessons)
    audio_key = (audio["editorial_key"],)
    exercise_key = (exercise["editorial_key"],)
    assert before["lesson_media"][audio_key]["listening_exercise_id"] == exercise_key

    review = courses[0]["units"][0]["review"]
    listening_lesson = next(
        item
        for item in lessons
        if item["course_slug"] == courses[0]["slug"]
        and item["number"] == review["listening_lesson_number"]
    )
    review_audio = next(
        item
        for item in listening_lesson["media"]
        if item["position"] == review["listening_media_position"]
    )
    review_key = (((courses[0]["slug"],), courses[0]["units"][0]["slug"]),)
    review_media_key = (review_audio["editorial_key"],)
    assert before["course_review"][review_key]["listening_media_id"] == review_media_key

    exercise["position"] = 999
    review_audio["position"] = 999
    after = seed_graph(courses, lessons)
    assert after["lesson_media"][audio_key]["listening_exercise_id"] == exercise_key
    assert after["course_review"][review_key]["listening_media_id"] == review_media_key


def test_listening_link_to_another_lesson_is_rejected_before_database():
    courses, lessons = package()
    lessons[1]["media"][0]["listening_exercise_key"] = lessons[0]["exercises"][0][
        "editorial_key"
    ]
    with pytest.raises(ValueError, match="outra aula"):
        seed_graph(courses, lessons)


async def test_blocked_seed_preserves_draft_revision_voice_answer_and_review(session):
    stored, ids = await read_graph(session)
    user = User(
        email="seed-safety@example.test", display_name="Synthetic", password_hash="not-a-password"
    )
    session.add(user)
    await session.flush()
    prompt_id = next(iter(ids["writing_prompt"].values()))
    draft = WritingDraft(user_id=user.id, prompt_id=prompt_id, text="PRIVATE DRAFT", revision=1)
    session.add(draft)
    await session.flush()
    session.add(WritingRevision(draft_id=draft.id, version=1, text="PRIVATE VERSION"))
    session.add(
        SpeakingAttempt(
            user_id=user.id,
            transcript_cue_id=next(iter(ids["transcript_cue"].values())),
            duration_ms=1200,
            storage_key="private-audio.webm",
        )
    )
    session.add(
        ExerciseAttempt(
            user_id=user.id,
            exercise_id=next(iter(ids["exercise"].values())),
            answer="PRIVATE ANSWER",
            correct=True,
        )
    )
    session.add(
        ReviewCardLegacy(
            user_id=user.id,
            vocab_item_id=next(iter(ids["vocab_item"].values())),
            due_at=datetime.now(UTC),
        )
    )
    await session.commit()
    models = (WritingDraft, WritingRevision, SpeakingAttempt, ExerciseAttempt, ReviewCardLegacy)

    async def personal():
        return {
            model.__tablename__: [
                dict(row)
                for row in (
                    await session.execute(select(model.__table__).order_by(model.id))
                ).mappings()
            ]
            for model in models
        }

    before = await personal()
    _, wanted = seed.load_seed_graph()
    for name in ("writing_prompt", "transcript_cue", "lesson_media", "exercise", "vocab_item"):
        wanted[name].clear()
    with pytest.raises(SeedBlocked) as blocked:
        await apply_graph(session, wanted)
    output = json.dumps(blocked.value.report, default=str)
    assert "PRIVATE" not in output and "private-audio" not in output
    assert "seed-safety@example" not in output
    assert await personal() == before
    after, _ = await read_graph(session)
    assert after == stored


@pytest.fixture
async def additive_package(session):
    courses, lessons = package()
    course = deepcopy(courses[0])
    course.update(slug="seed40-isolated-fixture", position=100, total_lessons=1)
    unit = deepcopy(course["units"][0])
    unit.update(slug="one", position=1, total_lessons=1, lesson_start=1, lesson_end=1)
    review = unit["review"]
    review.update(position=2, review_lesson_number=1)
    if review.get("listening_lesson_number") is not None:
        review.update(
            listening_lesson_number=1, listening_media_position=lessons[0]["media"][0]["position"]
        )
    for question in review["questions"]:
        question["lesson_numbers"] = [1]
        question["editorial_key"] = str(uuid4())
    course["units"] = [unit]
    lesson = deepcopy(lessons[0])
    lesson.update(course_slug=course["slug"], unit_slug="one", number=1, position=1)
    # A distinct authored entity requires a new key, not the original's identity.
    for field in ("exercises", "writing_prompts", "vocab", "media"):
        for item in lesson[field]:
            item["editorial_key"] = str(uuid4())
            for cue in item.get("cues", []):
                cue["editorial_key"] = str(uuid4())
    for media in lesson["media"]:
        target = next(
            exercise
            for exercise in lesson["exercises"]
            if exercise["position"] == media["listening_exercise_position"]
        )
        media["listening_exercise_key"] = target["editorial_key"]
    if review.get("listening_media_position") is not None:
        review["listening_media_key"] = next(
            media["editorial_key"]
            for media in lesson["media"]
            if media["position"] == review["listening_media_position"]
        )
    courses.append(course)
    lessons.append(lesson)
    try:
        yield courses, lessons
    finally:
        await session.rollback()
        # Exact synthetic course in the guarded disposable DB, never broad cleanup.
        course_id = select(Course.id).where(Course.slug == "seed40-isolated-fixture")
        unit_id = select(CourseUnit.id).where(CourseUnit.course_id.in_(course_id))
        await session.execute(delete(CourseReview).where(CourseReview.unit_id.in_(unit_id)))
        await session.execute(delete(Lesson).where(Lesson.course_id.in_(course_id)))
        await session.execute(delete(Course).where(Course.slug == "seed40-isolated-fixture"))
        await session.commit()


async def test_new_course_inserts_full_graph_and_reseed_is_noop(
    session, additive_package, monkeypatch
):
    courses, lessons = additive_package
    monkeypatch.setattr(seed, "load_course_seed", lambda path=None: courses)
    monkeypatch.setattr(seed, "load_seed", lambda path=None: lessons)
    assert await seed.seed_lessons(session) == 83
    stored, _ = await read_graph(session)
    assert compare_graphs(seed_graph(courses, lessons), stored)["changes"] == []
    before = await editorial_rows(session)
    assert await seed.seed_lessons(session) == 83
    assert await editorial_rows(session) == before


async def test_partial_insertion_failure_rolls_back_entire_batch(
    session, additive_package, monkeypatch
):
    courses, lessons = additive_package
    before = await editorial_rows(session)

    def fail_late(table):
        if table.name == "grammar_block":
            raise RuntimeError("Synthetic failure after new course/lesson inserts")
        return insert(table)

    monkeypatch.setattr(seed_plan, "insert", fail_late)
    with pytest.raises(RuntimeError, match="Synthetic failure"):
        await apply_graph(session, seed_graph(courses, lessons))
    assert await editorial_rows(session) == before


async def test_apply_rechecks_database_after_preview(session):
    report = await seed.preview_seed(session)
    assert report["allowed"]
    exercise_id, prompt = (
        await session.execute(select(Exercise.id, Exercise.prompt).limit(1))
    ).one()
    await session.rollback()
    async with get_sessionmaker()() as other:
        await other.execute(
            update(Exercise).where(Exercise.id == exercise_id).values(prompt="changed")
        )
        await other.commit()
        try:
            with pytest.raises(SeedBlocked):
                await seed.seed_lessons(session)
            assert (
                await session.scalar(select(Exercise.prompt).where(Exercise.id == exercise_id))
                == "changed"
            )
        finally:
            await session.rollback()
            await other.execute(
                update(Exercise).where(Exercise.id == exercise_id).values(prompt=prompt)
            )
            await other.commit()


async def test_busy_editorial_writer_refused_without_waiting(session):
    async with get_sessionmaker()() as other:
        await other.execute(text('LOCK TABLE "exercise" IN ROW EXCLUSIVE MODE'))
        try:
            with pytest.raises(DBAPIError) as blocked:
                await seed.seed_lessons(session)
            assert blocked.value.orig.sqlstate == "55P03"
        finally:
            await other.rollback()
    assert await seed.seed_lessons(session) == 82


async def test_preview_refuses_existing_transaction_and_apply_refuses_pending_orm(session):
    await session.execute(select(Course.id))
    with pytest.raises(ValueError, match="sessão nova"):
        await seed.preview_seed(session)
    await session.rollback()
    user = User(
        email="pending@example.test", display_name="Pending", password_hash="not-a-password"
    )
    session.add(user)
    with pytest.raises(ValueError, match="pendentes"):
        await seed.seed_lessons(session)
    assert user in session.new  # Caller owns it; never silently commit/discard.
    await session.rollback()


def test_diff_is_bounded_but_all_blockers_are_counted():
    _, wanted = seed.load_seed_graph()
    empty = {spec.name: {} for spec in SPECS}
    report = compare_graphs(empty, wanted)
    assert len(report["changes"]) == seed_plan.REPORT_LIMIT
    assert report["changes_truncated"] and not report["allowed"]
    assert report["counts"]["blocked"] == sum(len(rows) for rows in wanted.values())


async def test_old_repeatable_read_snapshot_cannot_authorize_apply(session):
    await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
    await session.execute(select(Course.id))
    with pytest.raises(ValueError, match="READ COMMITTED"):
        await seed.seed_lessons(session)
    assert not session.in_transaction()


async def test_old_editorial_metadata_is_retained_verbatim_without_blocking_noop(session):
    _, wanted = seed.load_seed_graph()
    _, ids = await read_graph(session)
    current = next(value for value in wanted["lesson_version"].values() if value["version"] > 1)
    lesson_key = current["lesson_id"]
    old_version = dict(
        current,
        version=current["version"] - 1,
        lesson_id=ids["lesson"][lesson_key],
        review_note="Synthetic historical note",
    )
    old_id = await session.scalar(
        insert(LessonVersion.__table__).values(**old_version).returning(LessonVersion.id)
    )
    await session.commit()
    try:
        before = await editorial_rows(session)
        await session.rollback()
        report = await seed.preview_seed(session)
        assert report["allowed"] and report["counts"]["retained"] == 1
        assert report["changes"][0]["reason"] == "historical_metadata_preserved"
        assert report["changes"][0]["fields"] == []
        assert await seed.seed_lessons(session) == 82
        assert await editorial_rows(session) == before
        # Downgrade to the old version cannot hide the newer one as retained.
        downgraded = deepcopy(wanted)
        new_key = (lesson_key, current["version"])
        del downgraded["lesson_version"][new_key]
        downgraded["lesson_version"][(lesson_key, old_version["version"])] = dict(
            old_version, lesson_id=lesson_key
        )
        with pytest.raises(SeedBlocked):
            await apply_graph(session, downgraded)
    finally:
        await session.rollback()
        await session.execute(delete(LessonVersion).where(LessonVersion.id == old_id))
        await session.commit()


async def test_public_seed_entry_blocks_removal_of_exercise_in_real_practice(
    client, session, monkeypatch
):
    from app.db.models import CourseReviewAttempt, PracticeSessionItem
    from tests.test_course_reviews import REVIEW_URL, attempt_body
    from tests.test_practice import conta, create_body

    headers = await conta(client, "seed-plan")
    practice = await client.post(
        "/api/courses/voa-level-1/lessons/31/practice-sessions", headers=headers, json=create_body()
    )
    assert practice.status_code == 201
    review = (await client.get(REVIEW_URL, headers=headers)).json()
    checkpoint = await client.post(
        f"{REVIEW_URL}/attempts", headers=headers, json=attempt_body(review)
    )
    assert checkpoint.status_code == 201
    before_items = list((await session.execute(select(PracticeSessionItem.__table__))).mappings())
    before_results = list((await session.execute(select(CourseReviewAttempt.__table__))).mappings())
    lessons = seed.load_seed()
    target = next(
        raw for raw in lessons if raw["course_slug"] == "voa-level-1" and raw["number"] == 31
    )
    linked_position = target["media"][0]["listening_exercise_position"]
    target["exercises"] = [
        exercise for exercise in target["exercises"] if exercise["position"] == linked_position
    ]
    monkeypatch.setattr(seed, "load_seed", lambda path=None: lessons)
    with pytest.raises(SeedBlocked):
        await seed.seed_lessons(session)
    assert (
        list((await session.execute(select(PracticeSessionItem.__table__))).mappings())
        == before_items
    )
    assert (
        list((await session.execute(select(CourseReviewAttempt.__table__))).mappings())
        == before_results
    )
