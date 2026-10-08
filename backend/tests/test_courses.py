"""Catálogo multi-curso e compatibilidade das rotas antigas."""

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Course, CourseUnit, Lesson


@pytest.mark.asyncio
async def test_catalogo_separa_planejado_de_publicado(client: AsyncClient) -> None:
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
        "published_lessons": 10,
    }
    assert courses[1]["total_lessons"] == 30
    assert courses[1]["published_lessons"] == 0
    assert courses[1]["status"] == "planned"


@pytest.mark.asyncio
async def test_curriculo_traz_unidades_e_resumos_leves(client: AsyncClient) -> None:
    response = await client.get("/api/courses/voa-level-1/curriculum")

    assert response.status_code == 200
    curriculum = response.json()
    assert curriculum["course"]["published_lessons"] == 10
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
    assert all(unit["lessons"] == [] for unit in curriculum["units"][1:])


@pytest.mark.asyncio
async def test_curso_inexistente_devolve_404(client: AsyncClient) -> None:
    assert (await client.get("/api/courses/inexistente/curriculum")).status_code == 404
    assert (await client.get("/api/courses/inexistente/lessons/31")).status_code == 404


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
    level_2 = courses["voa-level-2"]
    lessons = [
        Lesson(
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
        ),
        Lesson(
            course_id=level_2.id,
            unit_id=units[(level_2.id, "1-5")].id,
            number=1,
            slug="lesson-1",
            position=1,
            title="Level 2 lesson one",
            title_pt="Aula um do Level 2",
            voa_url="https://example.com/level-2/1",
            grammar_tag="Teste Level 2",
            focus_points=[],
            lead="Fixture temporária.",
            warmup_prompt="Warmup Level 2",
            listening_focus="Listening Level 2",
        ),
    ]
    session.add_all(lessons)
    await session.commit()
    ids = [lesson.id for lesson in lessons]

    try:
        legacy = await client.get("/api/lessons/1")
        level_2_response = await client.get("/api/courses/voa-level-2/lessons/1")

        assert legacy.status_code == level_2_response.status_code == 200
        assert legacy.json()["title"] == "Level 1 lesson one"
        assert level_2_response.json()["title"] == "Level 2 lesson one"
        assert level_2_response.json()["course_slug"] == "voa-level-2"
    finally:
        await session.execute(delete(Lesson).where(Lesson.id.in_(ids)))
        await session.commit()

