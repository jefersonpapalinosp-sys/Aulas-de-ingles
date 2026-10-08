"""O seed precisa poder rodar quantas vezes for preciso."""

from copy import deepcopy
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ContentSource,
    Course,
    CourseReview,
    CourseReviewQuestion,
    CourseUnit,
    Exercise,
    ExerciseAnswer,
    ExerciseHint,
    Lesson,
    LessonMedia,
    LessonVersion,
    TranscriptCue,
    VocabItem,
    WritingPrompt,
)
from app.db.seed import (
    load_course_seed,
    load_seed,
    seed_lessons,
    validate_course_reviews,
)


async def _contagens(session: AsyncSession) -> dict[str, int]:
    saida = {}
    for nome, modelo in (
        ("course", Course),
        ("course_unit", CourseUnit),
        ("course_review", CourseReview),
        ("course_review_question", CourseReviewQuestion),
        ("lesson", Lesson),
        ("lesson_media", LessonMedia),
        ("content_source", ContentSource),
        ("lesson_version", LessonVersion),
        ("transcript_cue", TranscriptCue),
        ("vocab_item", VocabItem),
        ("exercise", Exercise),
        ("exercise_answer", ExerciseAnswer),
        ("exercise_hint", ExerciseHint),
        ("writing_prompt", WritingPrompt),
    ):
        saida[nome] = (await session.execute(select(func.count()).select_from(modelo))).scalar_one()
    return saida


@pytest.mark.asyncio
async def test_arquivo_de_seed_tem_as_quatorze_aulas() -> None:
    dados = load_seed()
    assert [d["number"] for d in dados] == list(range(31, 45))
    assert sum(len(d["vocab"]) for d in dados) == 155
    assert sum(len(d["exercises"]) for d in dados) == 143
    assert sum(len(e.get("answers", [])) for d in dados for e in d["exercises"]) == 169
    assert sum(len(e.get("hints", [])) for d in dados for e in d["exercises"]) == 199
    assert sum(len(d.get("media", [])) for d in dados) == 14
    assert sum(len(d.get("writing_prompts", [])) for d in dados) == 14
    assert sum(len(m.get("cues", [])) for d in dados for m in d.get("media", [])) == 68
    assert sum(len(m.get("transcript", [])) for d in dados for m in d.get("media", [])) == 289
    media = [item for lesson in dados for item in lesson.get("media", [])]
    assert all(item["license_status"] == "public_domain" for item in media)
    assert all(item["offline_policy"] == "network_only" for item in media)
    assert all(item["attribution"] and item["license_url"] for item in media)
    assert all(item["license_reviewed_at"] == "2026-10-08" for item in media)
    assert all(d["editorial_status"] == "reviewed" for d in dados)
    assert all(d["learning_strategy"] for d in dados)
    assert all(d["course_slug"] == "voa-level-1" for d in dados)
    assert all(d["unit_slug"] == "31-40" for d in dados[:10])
    assert all(d["unit_slug"] == "40-44" for d in dados[10:])
    assert [d["position"] for d in dados[:10]] == list(range(1, 11))
    assert [d["position"] for d in dados[10:]] == list(range(1, 5))
    assert all(d["warmup_prompt"] and d["listening_focus"] for d in dados)

    pilots = [lesson for lesson in dados if lesson["number"] in {31, 38, 40}]
    allowed_objectives = {"recognize", "apply", "correct", "produce", "listen"}
    assert all(8 <= len(lesson["exercises"]) <= 12 for lesson in pilots)
    assert all(lesson["content_version"] == 2 for lesson in pilots)
    assert all(lesson.get("review_note", "").startswith("Sprint 21:") for lesson in pilots)
    assert all(
        exercise.get("objective") in allowed_objectives
        and len(exercise.get("hints", [])) == 2
        for lesson in pilots
        for exercise in lesson["exercises"]
    )


@pytest.mark.asyncio
async def test_seed_de_cursos_planeja_os_dois_niveis() -> None:
    courses = load_course_seed()

    assert [course["slug"] for course in courses] == ["voa-level-1", "voa-level-2"]
    assert [course["total_lessons"] for course in courses] == [52, 30]
    assert [len(course["units"]) for course in courses] == [4, 6]


def test_checkpoint_do_seed_valida_referencias_e_gabarito() -> None:
    courses = load_course_seed()
    lessons = load_seed()
    validate_course_reviews(courses, lessons)

    broken_lesson = deepcopy(courses)
    broken_lesson[0]["units"][1]["review"]["review_lesson_number"] = 999
    with pytest.raises(ValueError, match="Aula 999"):
        validate_course_reviews(broken_lesson, lessons)

    broken_media = deepcopy(courses)
    broken_media[0]["units"][1]["review"]["listening_media_position"] = 999
    with pytest.raises(ValueError, match="mídia inexistente"):
        validate_course_reviews(broken_media, lessons)

    broken_answer = deepcopy(courses)
    broken_answer[0]["units"][1]["review"]["questions"][0][
        "accepted_answers"
    ] = []
    with pytest.raises(ValueError, match="resposta aceita"):
        validate_course_reviews(broken_answer, lessons)

    broken_question_lessons = deepcopy(courses)
    broken_question_lessons[0]["units"][1]["review"]["questions"][0][
        "lesson_numbers"
    ] = []
    with pytest.raises(ValueError, match="ao menos uma aula"):
        validate_course_reviews(broken_question_lessons, lessons)


@pytest.mark.asyncio
async def test_seed_rodado_de_novo_nao_duplica(session: AsyncSession) -> None:
    antes = await _contagens(session)
    assert antes["course"] == 2
    assert antes["course_unit"] == 10
    assert antes["course_review"] == 1
    assert antes["course_review_question"] == 6
    assert antes["lesson"] == 14

    await seed_lessons(session)

    depois = await _contagens(session)
    assert depois == antes


@pytest.mark.asyncio
async def test_ids_de_aula_sobrevivem_ao_reseed(session: AsyncSession) -> None:
    before = {
        (lesson.course_slug, lesson.number): lesson.id
        for lesson in (await session.execute(select(Lesson))).scalars()
    }

    await seed_lessons(session)

    after = {
        (lesson.course_slug, lesson.number): lesson.id
        for lesson in (await session.execute(select(Lesson))).scalars()
    }
    assert after == before


@pytest.mark.asyncio
async def test_ids_do_checkpoint_sobrevivem_ao_reseed(session: AsyncSession) -> None:
    review_before_id = (await session.execute(select(CourseReview.id))).scalar_one()
    questions_before = {
        item.position: item.id
        for item in (await session.execute(select(CourseReviewQuestion))).scalars()
    }

    await seed_lessons(session)

    review_after = (await session.execute(select(CourseReview))).scalar_one()
    questions_after = {
        item.position: item.id
        for item in (await session.execute(select(CourseReviewQuestion))).scalars()
    }
    assert review_after.id == review_before_id
    assert questions_after == questions_before


@pytest.mark.asyncio
async def test_ids_de_vocabulario_sobrevivem_ao_reseed(session: AsyncSession) -> None:
    """A S4 vai pendurar cartas de revisão nesses ids — eles não podem trocar."""
    antes = {
        (v.lesson_id, v.term): v.id for v in (await session.execute(select(VocabItem))).scalars()
    }
    await seed_lessons(session)
    depois = {
        (v.lesson_id, v.term): v.id for v in (await session.execute(select(VocabItem))).scalars()
    }
    assert antes == depois


@pytest.mark.asyncio
async def test_ids_de_midia_e_trechos_sobrevivem_ao_reseed(session: AsyncSession) -> None:
    """Retomada e speaking apontam para esses IDs e não podem ser apagados pelo seed."""
    media_before = {
        (item.lesson_id, item.position): item.id
        for item in (await session.execute(select(LessonMedia))).scalars()
    }
    cues_before = {
        (item.media_id, item.position): item.id
        for item in (await session.execute(select(TranscriptCue))).scalars()
    }

    await seed_lessons(session)

    media_after = {
        (item.lesson_id, item.position): item.id
        for item in (await session.execute(select(LessonMedia))).scalars()
    }
    cues_after = {
        (item.media_id, item.position): item.id
        for item in (await session.execute(select(TranscriptCue))).scalars()
    }
    assert media_after == media_before
    assert cues_after == cues_before


@pytest.mark.asyncio
async def test_midia_persiste_licenca_e_politica_offline(session: AsyncSession) -> None:
    media = list((await session.execute(select(LessonMedia))).scalars())

    assert len(media) == 14
    assert all(item.license_status == "public_domain" for item in media)
    assert all(item.offline_policy == "network_only" for item in media)
    assert all(item.attribution == "Voice of America (VOA Learning English)" for item in media)
    assert all(
        item.license_url == "https://learningenglish.voanews.com/p/6021.html" for item in media
    )
    assert all(item.license_reviewed_at == date(2026, 10, 8) for item in media)


@pytest.mark.asyncio
async def test_exercicio_com_mais_de_uma_resposta_certa(session: AsyncSession) -> None:
    """Variantes corretas compartilham o mesmo exercício e o mesmo histórico."""
    lesson = (await session.execute(select(Lesson).where(Lesson.number == 31))).scalar_one()
    exercicio = next(e for e in lesson.exercises if e.position == 4)
    valores = {a.value for a in exercicio.answers}
    assert valores == {"a lot", "much", "far"}
