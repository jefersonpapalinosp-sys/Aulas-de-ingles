"""Fechamento do recorte: progresso, evidências e elegibilidade."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Course,
    CourseReview,
    CourseReviewAttempt,
    CourseUnit,
    Lesson,
    LessonProgress,
    StudySessionProgress,
    User,
)
from app.db.session import get_engine


async def conta(client: AsyncClient, suffix: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"{suffix}@example.com",
            "password": "senha-bem-grande",
            "display_name": suffix,
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def usuario(session: AsyncSession, suffix: str) -> User:
    return (
        await session.execute(select(User).where(User.email == f"{suffix}@example.com"))
    ).scalar_one()


async def level_one_lessons(session: AsyncSession) -> list[Lesson]:
    return list(
        (
            await session.execute(
                select(Lesson)
                .join(Course, Lesson.course_id == Course.id)
                .where(Course.slug == "voa-level-1")
                .order_by(Lesson.number)
            )
        ).scalars()
    )


async def published_reviews(session: AsyncSession) -> list[CourseReview]:
    return list(
        (
            await session.execute(
                select(CourseReview)
                .join(CourseUnit, CourseReview.unit_id == CourseUnit.id)
                .join(Course, CourseUnit.course_id == Course.id)
                .where(
                    Course.slug == "voa-level-1",
                    CourseUnit.status == "published",
                    CourseReview.status == "published",
                )
                .order_by(CourseUnit.position)
            )
        ).scalars()
    )


def review_attempt(user_id: int, review: CourseReview) -> CourseReviewAttempt:
    return CourseReviewAttempt(
        user_id=user_id,
        review_id=review.id,
        idempotency_key=str(uuid4()),
        request_hash="a" * 64,
        content_version=review.content_version,
        answers=[],
        result=[],
        score=1,
        total=1,
    )


@pytest.mark.asyncio
async def test_completion_exige_login_e_reconhece_recorte_publicado(client: AsyncClient) -> None:
    assert (await client.get("/api/courses/voa-level-1/completion")).status_code == 401

    headers = await conta(client, "completion-404")
    missing = await client.get("/api/courses/inexistente/completion", headers=headers)
    pilot = await client.get("/api/courses/voa-level-2/completion", headers=headers)

    assert missing.status_code == 404
    assert pilot.status_code == 200
    assert pilot.json()["progress"]["published_lessons"] == 25
    assert pilot.json()["checkpoints"]["published"] == 5
    assert pilot.json()["checkpoints"]["current_completed"] == 0
    assert [checkpoint["unit_slug"] for checkpoint in pilot.json()["checkpoints"]["pending"]] == [
        "1-5",
        "6-10",
        "11-15",
        "16-20",
        "21-25",
    ]
    assert pilot.json()["certificate"] == {
        **pilot.json()["certificate"],
        "eligible": False,
        "required_lessons": 30,
        "scope_label": "Aulas 1–30",
        "automatic_download": False,
    }
    assert missing.headers["cache-control"] == "private, no-store"
    assert pilot.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_completion_nao_materializa_conteudo_pesado(
    client: AsyncClient,
) -> None:
    """O resumo cresce em linhas, não nas relações editoriais de cada aula."""

    headers = await conta(client, "completion-query-budget")
    statements: list[str] = []
    sync_engine = get_engine().sync_engine

    def capture_sql(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement.lower())

    event.listen(sync_engine, "before_cursor_execute", capture_sql)
    try:
        response = await client.get("/api/courses/voa-level-1/completion", headers=headers)
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture_sql)

    assert response.status_code == 200
    assert len(statements) <= 12
    heavy_relations = (
        "lesson_goal",
        "grammar_block",
        "phrase",
        "vocab_item",
        "pronunciation_note",
        "course_review_question",
        "lesson_version",
        "content_source",
    )
    assert not any(
        relation in statement for relation in heavy_relations for statement in statements
    )


@pytest.mark.asyncio
async def test_completion_vazio_explica_regra_e_nao_muta_estado(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "completion-empty")
    user = await usuario(session, "completion-empty")
    user_id = user.id

    async def counts() -> tuple[int, int, int]:
        return (
            int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(LessonProgress)
                        .where(LessonProgress.user_id == user_id)
                    )
                ).scalar_one()
            ),
            int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(StudySessionProgress)
                        .where(StudySessionProgress.user_id == user_id)
                    )
                ).scalar_one()
            ),
            int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(CourseReviewAttempt)
                        .where(CourseReviewAttempt.user_id == user_id)
                    )
                ).scalar_one()
            ),
        )

    before = await counts()
    response = await client.get("/api/courses/voa-level-1/completion", headers=headers)
    after = await counts()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert before == after == (0, 0, 0)
    body = response.json()
    assert body["course"] == {
        "slug": "voa-level-1",
        "title": "Let's Learn English — Level 1",
        "level": "1",
        "proficiency_label": "Iniciante",
    }
    assert body["progress"] == {
        "published_lessons": 22,
        "viewed_lessons": 0,
        "completed_lessons": 0,
        "completion_percent": 0,
        "status": "not_started",
    }
    assert [unit["slug"] for unit in body["incomplete_units"]] == [
        "31-40",
        "40-44",
        "45-49",
        "50-52",
    ]
    assert body["checkpoints"]["published"] == 3
    assert body["checkpoints"]["current_completed"] == 0
    assert len(body["checkpoints"]["pending"]) == 3
    assert all(skill["samples"] == 0 for skill in body["skills"])
    assert all(skill["score_percent"] is None for skill in body["skills"])
    assert {skill["status"] for skill in body["skills"]} == {"insufficient"}
    assert body["certificate"] == {
        "eligible": False,
        "status": "ineligible",
        "reason": "Conclua 22 aulas do recorte para liberar o certificado.",
        "required_lessons": 22,
        "required_checkpoints": 3,
        "scope_label": "Aulas 31–52",
        "cta_label": "Continuar estudando",
        "cta_href": "/cursos/voa-level-1/unidades/31-40",
        "automatic_download": False,
    }
    assert body["next_course"]["slug"] == "voa-level-2"
    assert body["next_course"]["status"] == "published"
    assert body["next_course"]["recommended"] is True
    assert body["next_course"]["required"] is False
    assert body["next_course"]["href"] == "/cursos/voa-level-2"
    assert "Let's Learn English — Level 2" in body["next_course"]["preview"]
    assert body["next_course"]["diagnostic"]["href"] == (
        "/cursos/voa-level-1/conclusao#diagnostico"
    )


@pytest.mark.asyncio
async def test_viewed_e_uniao_de_sessao_e_conclusao_sem_promover_aula_52(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "completion-viewed")
    user = await usuario(session, "completion-viewed")
    lessons = {lesson.number: lesson for lesson in await level_one_lessons(session)}
    session.add(
        StudySessionProgress(
            user_id=user.id,
            lesson_id=lessons[31].id,
            current_step="preparar",
            completed_steps=[],
            total_seconds=0,
        )
    )
    session.add(LessonProgress(user_id=user.id, lesson_id=lessons[52].id))
    await session.commit()

    body = (await client.get("/api/courses/voa-level-1/completion", headers=headers)).json()

    assert body["progress"]["viewed_lessons"] == 2
    assert body["progress"]["completed_lessons"] == 1
    assert body["progress"]["status"] == "in_progress"
    assert body["certificate"]["eligible"] is False
    final_unit = next(item for item in body["incomplete_units"] if item["slug"] == "50-52")
    assert final_unit["viewed_lessons"] == 1
    assert final_unit["completed_lessons"] == 1


@pytest.mark.asyncio
async def test_completion_expoe_amostras_score_e_status_do_curso(
    client: AsyncClient,
) -> None:
    headers = await conta(client, "completion-skills")
    exercise = (await client.get("/api/exercises?lesson=31")).json()[0]
    for key, answer in enumerate(("faster", "definitely wrong", "faster"), start=1):
        attempt = await client.post(
            f"/api/exercises/{exercise['id']}/attempt",
            headers=headers,
            json={
                "answer": answer,
                "idempotency_key": f"24000000-0000-4000-8000-{key:012d}",
            },
        )
        assert attempt.status_code == 200

    body = (await client.get("/api/courses/voa-level-1/completion", headers=headers)).json()
    grammar = next(item for item in body["skills"] if item["skill"] == "grammar")

    assert body["progress"]["status"] == "in_progress"
    assert grammar["samples"] == 3
    assert grammar["score_percent"] == 67
    assert grammar["status"] == "steady"


@pytest.mark.asyncio
async def test_certificate_elegivel_exige_aulas_e_checkpoints_na_versao_atual(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "completion-eligible")
    user = await usuario(session, "completion-eligible")
    lessons = await level_one_lessons(session)
    reviews = await published_reviews(session)
    assert len(lessons) == 22
    assert len(reviews) == 3
    session.add_all([LessonProgress(user_id=user.id, lesson_id=lesson.id) for lesson in lessons])
    session.add_all([review_attempt(user.id, review) for review in reviews])
    await session.commit()

    body = (await client.get("/api/courses/voa-level-1/completion", headers=headers)).json()

    assert body["progress"] == {
        "published_lessons": 22,
        "viewed_lessons": 22,
        "completed_lessons": 22,
        "completion_percent": 100,
        "status": "completed",
    }
    assert body["incomplete_units"] == []
    assert body["checkpoints"] == {
        "published": 3,
        "current_completed": 3,
        "pending": [],
    }
    assert body["certificate"]["eligible"] is True
    assert body["certificate"]["status"] == "eligible"
    assert body["certificate"]["scope_label"] == "Aulas 31–52"
    assert body["certificate"]["cta_label"] == "Consultar revisão e certificado na VOA"
    assert body["certificate"]["cta_href"] == (
        "https://learningenglish.voanews.com/a/"
        "lets-learn-english-review-lessons-50-51-52/3805506.html"
    )
    assert body["certificate"]["automatic_download"] is False


@pytest.mark.asyncio
async def test_certificate_rejeita_quantidades_compensadas_entre_unidades(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "completion-unit-integrity")
    user = await usuario(session, "completion-unit-integrity")
    lessons = await level_one_lessons(session)
    reviews = await published_reviews(session)
    units = list(
        (
            await session.execute(
                select(CourseUnit)
                .join(Course, CourseUnit.course_id == Course.id)
                .where(Course.slug == "voa-level-1")
                .order_by(CourseUnit.position)
            )
        ).scalars()
    )
    original_totals = [unit.total_lessons for unit in units]
    session.add_all([LessonProgress(user_id=user.id, lesson_id=lesson.id) for lesson in lessons])
    session.add_all([review_attempt(user.id, review) for review in reviews])

    try:
        units[0].total_lessons -= 1
        units[1].total_lessons += 1
        await session.commit()

        body = (await client.get("/api/courses/voa-level-1/completion", headers=headers)).json()

        assert body["progress"]["completed_lessons"] == 22
        assert body["certificate"]["required_lessons"] == 22
        assert body["certificate"]["eligible"] is False
        assert "quantidade de aulas diferente" in body["certificate"]["reason"]
    finally:
        for unit, original_total in zip(units, original_totals, strict=True):
            unit.total_lessons = original_total
        await session.commit()


@pytest.mark.asyncio
async def test_tentativa_de_checkpoint_desatualizada_nao_libera_certificado(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await conta(client, "completion-stale")
    user = await usuario(session, "completion-stale")
    lessons = await level_one_lessons(session)
    reviews = await published_reviews(session)
    session.add_all([LessonProgress(user_id=user.id, lesson_id=lesson.id) for lesson in lessons])
    session.add_all([review_attempt(user.id, review) for review in reviews])
    await session.commit()

    stale_review = reviews[-1]
    original_version = stale_review.content_version
    try:
        stale_review.content_version = original_version + 1
        await session.commit()

        body = (await client.get("/api/courses/voa-level-1/completion", headers=headers)).json()

        assert body["checkpoints"]["current_completed"] == 2
        assert body["checkpoints"]["pending"] == [
            {
                "unit_slug": "50-52",
                "title": "Checkpoint 50–52",
                "content_version": original_version + 1,
                "href": "/cursos/voa-level-1/unidades/50-52/checkpoint",
            }
        ]
        assert body["certificate"]["eligible"] is False
        assert body["certificate"]["cta_href"].endswith("/unidades/50-52/checkpoint")
    finally:
        stale_review.content_version = original_version
        await session.commit()


@pytest.mark.asyncio
async def test_completion_isola_contas_e_cursos(client: AsyncClient, session: AsyncSession) -> None:
    first_headers = await conta(client, "completion-owner")
    second_headers = await conta(client, "completion-other")
    first_user = await usuario(session, "completion-owner")
    second_user = await usuario(session, "completion-other")
    lessons = await level_one_lessons(session)
    session.add_all(
        [LessonProgress(user_id=first_user.id, lesson_id=lesson.id) for lesson in lessons]
    )

    level_two = (
        await session.execute(select(Course).where(Course.slug == "voa-level-2"))
    ).scalar_one()
    foreign_lesson = (
        await session.execute(
            select(Lesson).where(
                Lesson.course_id == level_two.id,
                Lesson.number == 1,
            )
        )
    ).scalar_one()
    session.add(LessonProgress(user_id=second_user.id, lesson_id=foreign_lesson.id))
    await session.commit()

    try:
        owner = (
            await client.get("/api/courses/voa-level-1/completion", headers=first_headers)
        ).json()
        other = (
            await client.get("/api/courses/voa-level-1/completion", headers=second_headers)
        ).json()

        assert owner["progress"]["completed_lessons"] == 22
        assert other["progress"]["completed_lessons"] == 0
        assert other["progress"]["viewed_lessons"] == 0

        level_two_completion = (
            await client.get("/api/courses/voa-level-2/completion", headers=second_headers)
        ).json()
        assert level_two_completion["course"]["slug"] == "voa-level-2"
        assert level_two_completion["certificate"]["scope_label"] == "Aulas 1–30"
        assert "31–52" not in str(level_two_completion)
    finally:
        await session.rollback()
