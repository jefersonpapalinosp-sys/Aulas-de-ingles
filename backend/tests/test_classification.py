"""Contrato puro dos exercícios de classificação."""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Exercise, ExerciseAnswer, ExerciseAttempt, Lesson
from app.db.seed import validate_exercises
from app.domain.answers import (
    acertou,
    analisar_resposta,
    canonicalizar_classificacao,
    validar_e_canonicalizar_classificacao,
)


def test_classificacao_compara_json_sem_depender_da_ordem_das_chaves() -> None:
    accepted = ['{"careful":"adjective","carefully":"adverb"}']
    response = '{ "carefully": "ADVERB", "careful": "Adjective" }'

    assert acertou(response, accepted)
    assert canonicalizar_classificacao(response) == ('{"careful":"adjective","carefully":"adverb"}')
    assert analisar_resposta(response, accepted).category == "correct"


def test_classificacao_incorreta_nao_revela_o_gabarito() -> None:
    accepted = ['{"careful":"adjective","carefully":"adverb"}']
    feedback = analisar_resposta('{"careful":"adverb","carefully":"adverb"}', accepted)

    assert feedback.category == "word_choice"
    assert feedback.message == "Revise as categorias dos itens marcados e tente novamente."
    assert [token.status for token in feedback.tokens] == ["review", "keep"]


@pytest.mark.parametrize(
    "response",
    [
        '{"careful":"adjective"}',
        '{"careful":"adjective","carefully":"noun"}',
        '["careful", "carefully"]',
        '{"careful":"adjective","careful":"adverb"}',
    ],
)
def test_classificacao_rejeita_resposta_incompleta_ou_fora_do_contrato(
    response: str,
) -> None:
    with pytest.raises(ValueError):
        validar_e_canonicalizar_classificacao(
            response,
            ["careful", "carefully"],
            ["adjective", "adverb"],
        )


def test_validacao_editorial_aceita_classificacao_consistente() -> None:
    lesson = {
        "course_slug": "voa-level-2",
        "number": 6,
        "exercises": [
            {
                "position": 1,
                "activity_type": "classification",
                "classification_items": ["careful", "carefully"],
                "classification_categories": ["adjective", "adverb"],
                "answers": [
                    json.dumps(
                        {"careful": "adjective", "carefully": "adverb"},
                        separators=(",", ":"),
                    )
                ],
            }
        ],
    }

    validate_exercises([lesson])


def test_validacao_editorial_rejeita_gabarito_parcial() -> None:
    lesson = {
        "course_slug": "voa-level-2",
        "number": 6,
        "exercises": [
            {
                "position": 1,
                "activity_type": "classification",
                "classification_items": ["careful", "carefully"],
                "classification_categories": ["adjective", "adverb"],
                "answers": ['{"careful":"adjective"}'],
            }
        ],
    }

    with pytest.raises(ValueError, match="gabarito incompatível"):
        validate_exercises([lesson])


@pytest.mark.asyncio
async def test_api_publica_contrato_e_persiste_resposta_canonica(
    client: AsyncClient, session: AsyncSession
) -> None:
    lesson = (await session.execute(select(Lesson).where(Lesson.number == 31))).scalars().first()
    assert lesson is not None
    exercise = Exercise(
        lesson_id=lesson.id,
        position=999,
        activity_type="classification",
        skill="grammar",
        objective="recognize",
        options=None,
        classification_items=["careful", "carefully"],
        classification_categories=["adjective", "adverb"],
        prompt="Classifique as palavras.",
        explanation="Adjetivos descrevem nomes; advérbios modificam ações.",
    )
    session.add(exercise)
    await session.flush()
    session.add(
        ExerciseAnswer(
            exercise_id=exercise.id,
            position=0,
            value='{"careful":"adjective","carefully":"adverb"}',
        )
    )
    await session.commit()

    try:
        public = await client.get("/api/exercises?lesson=31")
        payload = next(item for item in public.json() if item["id"] == exercise.id)
        assert payload["classification_items"] == ["careful", "carefully"]
        assert payload["classification_categories"] == ["adjective", "adverb"]
        assert "answers" not in payload

        registration = await client.post(
            "/api/auth/register",
            json={
                "email": "classification@example.com",
                "password": "senha-bem-grande",
                "display_name": "Classification",
            },
        )
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        incomplete = await client.post(
            f"/api/exercises/{exercise.id}/attempt",
            headers=headers,
            json={
                "answer": '{"careful":"adjective"}',
                "idempotency_key": "00000000-0000-4000-8000-000000000001",
            },
        )
        assert incomplete.status_code == 422

        correct = await client.post(
            f"/api/exercises/{exercise.id}/attempt",
            headers=headers,
            json={
                "answer": '{ "carefully": "adverb", "careful": "adjective" }',
                "idempotency_key": "00000000-0000-4000-8000-000000000002",
            },
        )
        assert correct.status_code == 200, correct.text
        assert correct.json()["correct"] is True

        replay = await client.post(
            f"/api/exercises/{exercise.id}/attempt",
            headers=headers,
            json={
                "answer": '{"careful":"adjective", "carefully":"adverb"}',
                "idempotency_key": "00000000-0000-4000-8000-000000000002",
            },
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == correct.json()

        invalid_answers = [
            '{"careful":"noun","carefully":"adverb"}',
            '{"careful":"adjective","carefully":"adverb","extra":"adverb"}',
            "not-json",
        ]
        for index, answer in enumerate(invalid_answers, start=3):
            invalid = await client.post(
                f"/api/exercises/{exercise.id}/attempt",
                headers=headers,
                json={
                    "answer": answer,
                    "idempotency_key": f"00000000-0000-4000-8000-{index:012d}",
                },
            )
            assert invalid.status_code == 422

        stored = (
            await session.execute(
                select(ExerciseAttempt).where(ExerciseAttempt.exercise_id == exercise.id)
            )
        ).scalar_one()
        assert stored.answer == '{"careful":"adjective","carefully":"adverb"}'
    finally:
        await session.execute(delete(Exercise).where(Exercise.id == exercise.id))
        await session.commit()
