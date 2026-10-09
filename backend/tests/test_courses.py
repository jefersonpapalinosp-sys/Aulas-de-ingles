"""Catálogo multi-curso e compatibilidade das rotas antigas."""

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Course, CourseUnit, Lesson


@pytest.mark.asyncio
async def test_catalogo_publica_apenas_o_piloto_do_level_2(client: AsyncClient) -> None:
    response = await client.get("/api/courses")

    assert response.status_code == 200
    courses = response.json()
    assert [course["slug"] for course in courses] == ["voa-level-1", "voa-level-2"]
    assert courses[0] == {
        "id": courses[0]["id"],
        "slug": "voa-level-1",
        "title": "Let's Learn English — Level 1",
        "level": "1",
        "proficiency_label": "Iniciante",
        "provider": "VOA Learning English",
        "source_url": "https://learningenglish.voanews.com/p/5644.html",
        "position": 1,
        "status": "published",
        "total_lessons": 52,
        "published_lessons": 22,
    }
    assert courses[1]["total_lessons"] == 30
    assert courses[1]["published_lessons"] == 5
    assert courses[1]["status"] == "published"


@pytest.mark.asyncio
async def test_curriculo_traz_unidades_e_resumos_leves(client: AsyncClient) -> None:
    response = await client.get("/api/courses/voa-level-1/curriculum")

    assert response.status_code == 200
    curriculum = response.json()
    assert curriculum["course"]["published_lessons"] == 22
    assert [unit["slug"] for unit in curriculum["units"]] == [
        "31-40",
        "40-44",
        "45-49",
        "50-52",
    ]
    first = curriculum["units"][0]
    assert first["total_lessons"] == first["published_lessons"] == 10
    assert [lesson["number"] for lesson in first["lessons"]] == list(range(31, 41))
    assert first["lessons"][0] == {
        "id": first["lessons"][0]["id"],
        "course_slug": "voa-level-1",
        "unit_slug": "31-40",
        "slug": "lesson-31",
        "position": 1,
        "number": 31,
        "title": "Take Me Out to the Ball Game",
        "title_pt": "Me leva pro jogo de beisebol",
        "grammar_tag": "Comparativos + conselho",
        "focus_points": ["should / ought to", "-er than", "a lot + comparativo"],
        "story_note": None,
    }
    assert "grammar_blocks" not in first["lessons"][0]
    second = curriculum["units"][1]
    assert second["total_lessons"] == second["published_lessons"] == 4
    assert [lesson["number"] for lesson in second["lessons"]] == list(range(41, 45))
    assert all(lesson["unit_slug"] == "40-44" for lesson in second["lessons"])
    assert second["review"] == {
        "id": second["review"]["id"],
        "slug": "checkpoint-40-44",
        "title": "Checkpoint 40–44",
        "position": 5,
        "status": "published",
        "source_kind": "mixed",
        "estimated_minutes": 12,
        "review_lesson_number": 40,
        "question_count": 6,
    }
    assert first["review"] is None
    third = curriculum["units"][2]
    assert third["total_lessons"] == third["published_lessons"] == 5
    assert [lesson["number"] for lesson in third["lessons"]] == list(range(45, 50))
    assert all(lesson["unit_slug"] == "45-49" for lesson in third["lessons"])
    assert third["review"]["slug"] == "checkpoint-45-49"
    assert third["review"]["question_count"] == 6
    fourth = curriculum["units"][3]
    assert fourth["total_lessons"] == fourth["published_lessons"] == 3
    assert [lesson["number"] for lesson in fourth["lessons"]] == [50, 51, 52]
    assert all(lesson["unit_slug"] == "50-52" for lesson in fourth["lessons"])
    assert fourth["review"]["slug"] == "checkpoint-50-52"
    assert fourth["review"]["review_lesson_number"] == 52
    assert fourth["review"]["question_count"] == 6


@pytest.mark.asyncio
async def test_curso_inexistente_devolve_404(client: AsyncClient) -> None:
    assert (await client.get("/api/courses/inexistente/curriculum")).status_code == 404
    assert (await client.get("/api/courses/inexistente/lessons/31")).status_code == 404


@pytest.mark.asyncio
async def test_curriculo_level_2_publica_1_a_5_e_mantem_futuras_em_preparacao(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/courses/voa-level-2/curriculum")

    assert response.status_code == 200
    curriculum = response.json()
    assert curriculum["course"]["status"] == "published"
    assert curriculum["course"]["published_lessons"] == 5
    assert [unit["slug"] for unit in curriculum["units"]] == [
        "1-5",
        "6-10",
        "11-15",
        "16-20",
        "21-25",
        "26-30",
    ]
    first, *future = curriculum["units"]
    assert first["status"] == "published"
    assert [lesson["number"] for lesson in first["lessons"]] == [1, 2, 3, 4, 5]
    assert first["review"]["slug"] == "checkpoint-1-5"
    assert first["review"]["question_count"] == 6
    assert all(unit["status"] == "planned" for unit in future)
    assert all(unit["published_lessons"] == 0 and unit["lessons"] == [] for unit in future)
    assert curriculum["units"][-1]["review"] is None


@pytest.mark.asyncio
async def test_detalhe_canonico_e_legado_apontam_para_mesma_aula(client: AsyncClient) -> None:
    canonical = await client.get("/api/courses/voa-level-1/lessons/31")
    legacy = await client.get("/api/lessons/31")

    assert canonical.status_code == legacy.status_code == 200
    assert canonical.json() == legacy.json()
    assert canonical.json()["course_slug"] == "voa-level-1"
    assert canonical.json()["unit_slug"] == "31-40"
    assert canonical.json()["warmup_prompt"].startswith("Como você compararia")
    assert canonical.json()["listening_focus"].startswith("os transportes")


@pytest.mark.asyncio
async def test_mesmo_numero_pode_existir_em_dois_cursos(
    client: AsyncClient, session: AsyncSession
) -> None:
    courses = {
        course.slug: course for course in (await session.execute(select(Course))).scalars()
    }
    units = {
        (unit.course_id, unit.slug): unit
        for unit in (await session.execute(select(CourseUnit))).scalars()
    }
    level_1 = courses["voa-level-1"]
    level_1_fixture = Lesson(
        course_id=level_1.id,
        unit_id=units[(level_1.id, "31-40")].id,
        number=1,
        slug="legacy-level-1-lesson-1",
        position=100,
        title="Level 1 lesson one",
        title_pt="Aula um do Level 1",
        voa_url="https://example.com/level-1/1",
        grammar_tag="Teste Level 1",
        focus_points=[],
        lead="Fixture temporária.",
        warmup_prompt="Warmup Level 1",
        listening_focus="Listening Level 1",
    )
    session.add(level_1_fixture)
    await session.commit()

    try:
        legacy = await client.get("/api/lessons/1")
        level_2_response = await client.get("/api/courses/voa-level-2/lessons/1")

        assert legacy.status_code == level_2_response.status_code == 200
        assert legacy.json()["title"] == "Level 1 lesson one"
        assert level_2_response.json()["title"] == "Budget Cuts"
        assert level_2_response.json()["course_slug"] == "voa-level-2"
        assert legacy.json()["id"] != level_2_response.json()["id"]
    finally:
        await session.execute(delete(Lesson).where(Lesson.id == level_1_fixture.id))
        await session.commit()


@pytest.mark.asyncio
async def test_aula_em_unidade_planejada_nao_vaza_nas_rotas_publicas(
    client: AsyncClient, session: AsyncSession
) -> None:
    level_2 = (
        await session.execute(select(Course).where(Course.slug == "voa-level-2"))
    ).scalar_one()
    future_unit = (
        await session.execute(
            select(CourseUnit).where(
                CourseUnit.course_id == level_2.id,
                CourseUnit.slug == "6-10",
            )
        )
    ).scalar_one()
    accidental = Lesson(
        course_id=level_2.id,
        unit_id=future_unit.id,
        number=6,
        slug="unpublished-fixture",
        position=1,
        title="Unpublished fixture",
        title_pt="Fixture não publicada",
        voa_url="https://example.com/unpublished",
        grammar_tag="Não publicado",
        focus_points=[],
        lead="Conteúdo em preparação.",
        warmup_prompt="Teste.",
        listening_focus="Teste.",
    )
    session.add(accidental)
    await session.commit()

    try:
        curriculum = (
            await client.get("/api/courses/voa-level-2/curriculum")
        ).json()
        unit = next(item for item in curriculum["units"] if item["slug"] == "6-10")
        assert unit["published_lessons"] == 0
        assert unit["lessons"] == []
        assert (
            await client.get("/api/courses/voa-level-2/lessons/6")
        ).status_code == 404
        assert (
            await client.get("/api/exercises?course=voa-level-2&lesson=6")
        ).json() == []
    finally:
        await session.execute(delete(Lesson).where(Lesson.id == accidental.id))
        await session.commit()
