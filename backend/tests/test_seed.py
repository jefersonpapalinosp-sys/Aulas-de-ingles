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
async def test_arquivo_de_seed_tem_quarenta_e_duas_aulas_em_dois_cursos() -> None:
    dados = load_seed()
    level_1 = [lesson for lesson in dados if lesson["course_slug"] == "voa-level-1"]
    level_2 = [lesson for lesson in dados if lesson["course_slug"] == "voa-level-2"]
    assert [d["number"] for d in level_1] == list(range(31, 53))
    assert [d["number"] for d in level_2] == list(range(1, 21))

    # O conteúdo publicado nas Sprints anteriores não pode ser reduzido durante
    # a expansão. As contagens novas são verificadas por aula, evitando acoplar
    # o teste ao tamanho editorial de transcrições e gabaritos.
    anteriores = level_1[:14]
    assert sum(len(d["vocab"]) for d in anteriores) == 155
    assert sum(len(d["exercises"]) for d in anteriores) == 143
    assert sum(len(e.get("answers", [])) for d in anteriores for e in d["exercises"]) == 169
    assert sum(len(e.get("hints", [])) for d in anteriores for e in d["exercises"]) == 199
    assert sum(len(d.get("media", [])) for d in anteriores) == 14
    assert sum(len(d.get("writing_prompts", [])) for d in anteriores) == 14
    assert sum(len(m.get("cues", [])) for d in anteriores for m in d.get("media", [])) == 68
    assert sum(len(m.get("transcript", [])) for d in anteriores for m in d.get("media", [])) == 289

    novas = level_1[14:]
    assert [d["number"] for d in novas] == list(range(45, 53))
    assert all(len(d["vocab"]) == 10 for d in novas)
    assert all(len(d["exercises"]) == 8 for d in novas)
    assert all(len(d.get("media", [])) == 1 for d in novas)
    assert all(len(d["media"][0].get("cues", [])) == 5 for d in novas)
    assert all(len(d.get("writing_prompts", [])) == 1 for d in novas)

    finais = level_1[19:]
    assert [d["number"] for d in finais] == [50, 51, 52]
    assert all(len(d["goals"]) == 4 for d in finais)
    assert all(len(d["grammar_blocks"]) == 3 for d in finais)
    assert all(len(d["phrases"]) == 5 for d in finais)
    assert all(len(d["pronunciation"]) == 3 for d in finais)
    assert all(d["media"][0].get("transcript", []) == [] for d in finais)
    assert [
        (
            lesson["number"],
            lesson["voa_url"],
            lesson["media"][0]["source_url"],
            lesson["media"][0]["duration_seconds"],
        )
        for lesson in finais
    ] == [
        (
            50,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-lesson-50-back-to-school/3771173.html",
            "https://voa-audio.voanews.eu/vle/2017/04/28/"
            "c26515f8-0d7c-4fb4-9646-4dfece722172_hq.mp3",
            201,
        ),
        (
            51,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-lesson-51-a-good-habit/3773577.html",
            "https://voa-audio.voanews.eu/vle/2017/04/06/"
            "1f484880-f858-47b5-8e0d-37a063b34a07_hq.mp3",
            185,
        ),
        (
            52,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-lesson-52-taking-chances/3805454.html",
            "https://voa-audio.voanews.eu/vle/2017/04/14/"
            "8259e341-9066-4896-af3d-f62d738d0948_hq.mp3",
            221,
        ),
    ]
    assert all(
        sum(exercise["skill"] == "listening" for exercise in lesson["exercises"]) == 4
        for lesson in finais
    )
    assert all(d.get("review_note", "").startswith("Sprint 24:") for d in finais)
    media = [item for lesson in dados for item in lesson.get("media", [])]
    assert all(item["license_status"] == "public_domain" for item in media)
    assert all(item["offline_policy"] == "network_only" for item in media)
    assert all(item["attribution"] and item["license_url"] for item in media)
    assert sum(item["license_reviewed_at"] == "2026-10-08" for item in media) == 27
    assert sum(item["license_reviewed_at"] == "2026-10-09" for item in media) == 15
    assert all(d["editorial_status"] == "reviewed" for d in dados)
    assert all(d["learning_strategy"] for d in dados)
    assert all(d["unit_slug"] == "31-40" for d in level_1[:10])
    assert all(d["unit_slug"] == "40-44" for d in level_1[10:14])
    assert all(d["unit_slug"] == "45-49" for d in level_1[14:19])
    assert all(d["unit_slug"] == "50-52" for d in level_1[19:])
    assert [d["position"] for d in level_1[:10]] == list(range(1, 11))
    assert [d["position"] for d in level_1[10:14]] == list(range(1, 5))
    assert [d["position"] for d in level_1[14:19]] == list(range(1, 6))
    assert [d["position"] for d in level_1[19:]] == list(range(1, 4))
    assert all(d["unit_slug"] == "1-5" for d in level_2[:5])
    assert all(d["unit_slug"] == "6-10" for d in level_2[5:10])
    assert all(d["unit_slug"] == "11-15" for d in level_2[10:15])
    assert all(d["unit_slug"] == "16-20" for d in level_2[15:])
    assert [d["position"] for d in level_2[:5]] == list(range(1, 6))
    assert [d["position"] for d in level_2[5:10]] == list(range(1, 6))
    assert [d["position"] for d in level_2[10:15]] == list(range(1, 6))
    assert [d["position"] for d in level_2[15:]] == list(range(1, 6))
    assert all(len(d["goals"]) == 4 for d in level_2)
    assert all(len(d["grammar_blocks"]) == 3 for d in level_2)
    assert all(len(d["phrases"]) == 5 for d in level_2)
    assert all(len(d["vocab"]) == 10 for d in level_2)
    assert all(len(d["pronunciation"]) == 3 for d in level_2)
    assert all(len(d["exercises"]) == 8 for d in level_2)
    assert all(len(d.get("writing_prompts", [])) == 1 for d in level_2)
    assert all(len(d.get("media", [])) == 1 for d in level_2)
    assert all(len(d["media"][0]["cues"]) == 5 for d in level_2)
    assert all(d["media"][0]["transcript"] == [] for d in level_2)
    assert all(
        sum(exercise["skill"] == "listening" for exercise in lesson["exercises"]) == 4
        for lesson in level_2
    )
    assert all(d.get("review_note", "").startswith("Sprint 25:") for d in level_2[:5])
    assert all(d.get("review_note", "").startswith("Sprint 26:") for d in level_2[5:10])
    assert all(d.get("review_note", "").startswith("Sprint 27:") for d in level_2[10:15])
    assert all(d.get("review_note", "").startswith("Sprint 28:") for d in level_2[15:])
    assert [d["media"][0]["duration_seconds"] for d in level_2[5:10]] == [
        284,
        237,
        300,
        266,
        237,
    ]
    assert [
        (
            lesson["number"],
            lesson["voa_url"],
            lesson["media"][0]["source_url"],
            lesson["media"][0]["duration_seconds"],
        )
        for lesson in level_2[10:15]
    ] == [
        (
            11,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-level-2-lesson-11-the-big-snow/4102755.html",
            "https://voa-audio.voanews.eu/vle/2017/11/21/"
            "0117495a-4165-48c3-8972-61491413ad7a_hq.mp3",
            267,
        ),
        (
            12,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-level-2-lesson-12-run-bees/4139015.html",
            "https://voa-audio.voanews.eu/vle/2017/11/28/"
            "260c25bd-1773-42d0-8b8a-54924d27427c_hq.mp3",
            258,
        ),
        (
            13,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-level-2-lesson-13-save-the-bees/4145716.html",
            "https://voa-audio.voanews.eu/vle/2017/12/01/"
            "104a6627-290a-4472-911e-3bb9349f44f7_hq.mp3",
            231,
        ),
        (
            14,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-level-2-lesson-14-made-for-each-other/4159000.html",
            "https://voa-audio.voanews.eu/vle/2017/12/12/"
            "e2fe076d-3fa7-495a-83ea-9d4d4cba9fad_hq.mp3",
            276,
        ),
        (
            15,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-level-2-lesson-15-before-after/4159057.html",
            "https://voa-audio.voanews.eu/vle/2018/01/04/"
            "99ceaa2e-fb25-43a8-8731-0a7f23901d65_hq.mp3",
            249,
        ),
    ]
    assert [
        (
            lesson["number"],
            lesson["voa_url"],
            lesson["media"][0]["source_url"],
            lesson["media"][0]["duration_seconds"],
        )
        for lesson in level_2[15:]
    ] == [
        (
            16,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-level-2-lesson-16/4198066.html",
            "https://voa-audio.voanews.eu/vle/"
            "2018/01/10/95f0ce1f-6cfd-44e4-b83a-e225d7cb0224_hq.mp3",
            281,
        ),
        (
            17,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-level-2-lesson-17/4220576.html",
            "https://voa-audio.voanews.eu/vle/"
            "2018/01/24/4f5af081-e654-4912-9f5d-24cd3fa5170a_hq.mp3",
            238,
        ),
        (
            18,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-level-2-lesson-18/4231290.html",
            "https://voa-audio.voanews.eu/vle/"
            "2018/01/31/16d806b3-f878-4eff-bd6e-1857ec1241e0_hq.mp3",
            258,
        ),
        (
            19,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-level-2-lesson-19/4242927.html",
            "https://voa-audio.voanews.eu/vle/"
            "2018/02/08/aa7b1559-adea-4534-8d4f-649785319a21_hq.mp3",
            287,
        ),
        (
            20,
            "https://learningenglish.voanews.com/a/"
            "lets-learn-english-level-2-lesson-20/4254704.html",
            "https://voa-audio.voanews.eu/vle/"
            "2018/02/15/8b42c321-07ea-4eb1-a1f9-e7cc6019606e_hq.mp3",
            281,
        ),
    ]
    assert level_2[7]["media"][0]["source_url"].endswith("_240p.mp4")
    adjective_adverb = next(
        exercise
        for exercise in level_2[7]["exercises"]
        if exercise["activity_type"] == "classification"
    )
    assert adjective_adverb["classification_categories"] == ["adjective", "adverb"]
    assert adjective_adverb["classification_items"] == [
        "secret",
        "seriously",
        "loyal",
        "strongly",
    ]
    classifications = [
        exercise
        for lesson in level_2[5:10]
        for exercise in lesson["exercises"]
        if exercise["activity_type"] == "classification"
    ]
    assert [
        lesson["number"]
        for lesson in level_2[5:10]
        for exercise in lesson["exercises"]
        if exercise["activity_type"] == "classification"
    ] == [6, 8, 10]
    assert all(len(exercise["answers"]) == 1 for exercise in classifications)
    sprint_27_classifications = [
        exercise
        for lesson in level_2[10:15]
        for exercise in lesson["exercises"]
        if exercise["activity_type"] == "classification"
    ]
    assert [
        lesson["number"]
        for lesson in level_2[10:15]
        for exercise in lesson["exercises"]
        if exercise["activity_type"] == "classification"
    ] == [11, 12, 15]
    # Sprint 28: todas as cinco aulas trazem uma classificação.
    assert [
        lesson["number"]
        for lesson in level_2[15:]
        for exercise in lesson["exercises"]
        if exercise["activity_type"] == "classification"
    ] == [16, 17, 18, 19, 20]
    assert len(sprint_27_classifications) == 3
    assert all(len(exercise["answers"]) == 1 for exercise in sprint_27_classifications)
    assert all(d["warmup_prompt"] and d["listening_focus"] for d in dados)

    pilots = [lesson for lesson in level_1 if lesson["number"] in {31, 38, 40}]
    allowed_objectives = {"recognize", "apply", "correct", "produce", "listen"}
    assert all(8 <= len(lesson["exercises"]) <= 12 for lesson in pilots)
    assert all(lesson["content_version"] == 2 for lesson in pilots)
    assert all(lesson.get("review_note", "").startswith("Sprint 21:") for lesson in pilots)
    assert all(
        exercise.get("objective") in allowed_objectives and len(exercise.get("hints", [])) == 2
        for lesson in pilots
        for exercise in lesson["exercises"]
    )


@pytest.mark.asyncio
async def test_seed_de_cursos_publica_as_quatro_primeiras_unidades_do_level_2() -> None:
    courses = load_course_seed()

    assert [course["slug"] for course in courses] == ["voa-level-1", "voa-level-2"]
    assert [course["total_lessons"] for course in courses] == [52, 30]
    assert [len(course["units"]) for course in courses] == [4, 6]
    assert [course["status"] for course in courses] == ["published", "published"]
    assert [unit["status"] for unit in courses[1]["units"]] == [
        "published",
        "published",
        "published",
        "published",
        "planned",
        "planned",
    ]


def test_checkpoint_do_seed_valida_referencias_e_gabarito() -> None:
    courses = load_course_seed()
    lessons = load_seed()
    validate_course_reviews(courses, lessons)

    reviews = [
        unit["review"]
        for course in courses
        for unit in course["units"]
        if unit.get("review") is not None
    ]
    assert [review["slug"] for review in reviews] == [
        "checkpoint-40-44",
        "checkpoint-45-49",
        "checkpoint-50-52",
        "checkpoint-1-5",
        "checkpoint-6-10",
        "checkpoint-11-15",
        "checkpoint-16-20",
    ]
    assert all(len(review["questions"]) == 6 for review in reviews)

    review_unit_index = next(
        index
        for index, unit in enumerate(courses[0]["units"])
        if (unit.get("review") or {}).get("slug") == "checkpoint-45-49"
    )

    broken_lesson = deepcopy(courses)
    broken_lesson[0]["units"][review_unit_index]["review"]["review_lesson_number"] = 999
    with pytest.raises(ValueError, match="Aula 999"):
        validate_course_reviews(broken_lesson, lessons)

    broken_media = deepcopy(courses)
    broken_media[0]["units"][review_unit_index]["review"]["listening_media_position"] = 999
    with pytest.raises(ValueError, match="mídia inexistente"):
        validate_course_reviews(broken_media, lessons)

    broken_answer = deepcopy(courses)
    broken_answer[0]["units"][review_unit_index]["review"]["questions"][0]["accepted_answers"] = []
    with pytest.raises(ValueError, match="resposta aceita"):
        validate_course_reviews(broken_answer, lessons)

    broken_question_lessons = deepcopy(courses)
    broken_question_lessons[0]["units"][review_unit_index]["review"]["questions"][0][
        "lesson_numbers"
    ] = []
    with pytest.raises(ValueError, match="ao menos uma aula"):
        validate_course_reviews(broken_question_lessons, lessons)


def test_catalogo_do_seed_valida_faixa_quantidade_e_posicao_das_aulas() -> None:
    courses = load_course_seed()
    lessons = load_seed()

    outside_range = deepcopy(lessons)
    final_level_1 = next(
        lesson
        for lesson in outside_range
        if lesson["course_slug"] == "voa-level-1" and lesson["number"] == 52
    )
    final_level_1["number"] = 53
    with pytest.raises(ValueError, match="fora da faixa 50–52"):
        validate_course_reviews(courses, outside_range)

    missing_lesson = deepcopy(
        [
            lesson
            for lesson in lessons
            if not (lesson["course_slug"] == "voa-level-1" and lesson["number"] == 52)
        ]
    )
    with pytest.raises(ValueError, match="declara 3 aulas, mas possui 2"):
        validate_course_reviews(courses, missing_lesson)

    skipped_position = deepcopy(lessons)
    skipped_position[-1]["position"] = 4
    with pytest.raises(ValueError, match="posições de aula não contíguas"):
        validate_course_reviews(courses, skipped_position)

    leaked_planned = deepcopy(lessons)
    leaked = deepcopy(next(lesson for lesson in lessons if lesson["course_slug"] == "voa-level-2"))
    leaked.update({"unit_slug": "21-25", "number": 21, "position": 1, "slug": "lesson-21"})
    leaked_planned.append(leaked)
    with pytest.raises(ValueError, match="Unidade em preparação.*não pode conter aulas"):
        validate_course_reviews(courses, leaked_planned)


@pytest.mark.asyncio
async def test_seed_rodado_de_novo_nao_duplica(session: AsyncSession) -> None:
    antes = await _contagens(session)
    assert antes["course"] == 2
    assert antes["course_unit"] == 10
    assert antes["course_review"] == 7
    assert antes["course_review_question"] == 42
    assert antes["lesson"] == 42

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
    reviews_before = {
        item.unit_id: item.id for item in (await session.execute(select(CourseReview))).scalars()
    }
    questions_before = {
        (item.review_id, item.position): item.id
        for item in (await session.execute(select(CourseReviewQuestion))).scalars()
    }
    assert len(reviews_before) == 7
    assert len(questions_before) == 42

    await seed_lessons(session)

    reviews_after = {
        item.unit_id: item.id for item in (await session.execute(select(CourseReview))).scalars()
    }
    questions_after = {
        (item.review_id, item.position): item.id
        for item in (await session.execute(select(CourseReviewQuestion))).scalars()
    }
    assert reviews_after == reviews_before
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

    assert len(media) == 42
    assert all(item.license_status == "public_domain" for item in media)
    assert all(item.offline_policy == "network_only" for item in media)
    assert all(item.attribution == "Voice of America (VOA Learning English)" for item in media)
    assert {item.license_url for item in media} <= {
        "https://learningenglish.voanews.com/p/6021.html",
        "https://learningenglish.voanews.com/p/6861.html",
    }
    assert sum(item.license_reviewed_at == date(2026, 10, 8) for item in media) == 27
    assert sum(item.license_reviewed_at == date(2026, 10, 9) for item in media) == 15


@pytest.mark.asyncio
async def test_exercicio_com_mais_de_uma_resposta_certa(session: AsyncSession) -> None:
    """Variantes corretas compartilham o mesmo exercício e o mesmo histórico."""
    lesson = (await session.execute(select(Lesson).where(Lesson.number == 31))).scalar_one()
    exercicio = next(e for e in lesson.exercises if e.position == 4)
    valores = {a.value for a in exercicio.answers}
    assert valores == {"a lot", "much", "far"}
