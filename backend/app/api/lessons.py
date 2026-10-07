"""Leitura do conteúdo das aulas. Tudo público nesta sprint."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Exercise, Lesson, VocabItem
from app.db.session import get_session
from app.domain.answers import acertou
from app.schemas.lesson import (
    CheckAnswerIn,
    CheckAnswerOut,
    ExerciseOut,
    ExerciseWithLessonOut,
    LessonDetailOut,
    LessonSummaryOut,
    RevealAnswerOut,
    VocabItemOut,
    VocabItemWithLessonOut,
)

router = APIRouter(tags=["lessons"])


@router.get("/lessons", response_model=list[LessonSummaryOut])
async def listar_aulas(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Lesson]:
    """Todas as aulas, em ordem, com o mínimo para montar a navegação."""
    result = await session.execute(select(Lesson).order_by(Lesson.number))
    return list(result.scalars())


@router.get("/lessons/{number}", response_model=LessonDetailOut)
async def obter_aula(
    number: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Lesson:
    """Uma aula inteira: gramática, frases, vocabulário, pronúncia e exercícios."""
    lesson = (
        await session.execute(select(Lesson).where(Lesson.number == number))
    ).scalar_one_or_none()
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Aula {number} não existe."
        )
    return lesson


@router.get("/vocab", response_model=list[VocabItemWithLessonOut])
async def listar_vocabulario(
    session: Annotated[AsyncSession, Depends(get_session)],
    lesson: Annotated[int | None, Query(description="Filtra por número da aula.")] = None,
) -> list[VocabItemWithLessonOut]:
    """Vocabulário de uma aula, ou de todas. Base do deck de revisão da S4."""
    stmt = (
        select(VocabItem, Lesson.number)
        .join(Lesson, VocabItem.lesson_id == Lesson.id)
        .order_by(Lesson.number, VocabItem.position)
    )
    if lesson is not None:
        stmt = stmt.where(Lesson.number == lesson)
    return [
        VocabItemWithLessonOut(
            **VocabItemOut.model_validate(item).model_dump(), lesson_number=numero
        )
        for item, numero in (await session.execute(stmt)).all()
    ]


@router.get("/exercises", response_model=list[ExerciseWithLessonOut])
async def listar_exercicios(
    session: Annotated[AsyncSession, Depends(get_session)],
    lesson: Annotated[int | None, Query(description="Filtra por número da aula.")] = None,
) -> list[ExerciseWithLessonOut]:
    """Exercícios de uma aula, ou do bloco inteiro.

    É o que a prova do bloco consome: sem isso a tela teria que baixar as dez
    aulas inteiras para montar uma lista de exercícios.
    """
    stmt = (
        select(Exercise, Lesson.number)
        .join(Lesson, Exercise.lesson_id == Lesson.id)
        .order_by(Lesson.number, Exercise.position)
    )
    if lesson is not None:
        stmt = stmt.where(Lesson.number == lesson)
    return [
        ExerciseWithLessonOut(
            **ExerciseOut.model_validate(item).model_dump(), lesson_number=numero
        )
        for item, numero in (await session.execute(stmt)).all()
    ]


async def _buscar_exercicio(session: AsyncSession, exercise_id: int) -> Exercise:
    exercicio = (
        await session.execute(select(Exercise).where(Exercise.id == exercise_id))
    ).scalar_one_or_none()
    if exercicio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Exercício {exercise_id} não existe."
        )
    return exercicio


@router.post("/exercises/{exercise_id}/check", response_model=CheckAnswerOut)
async def conferir_resposta(
    exercise_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[CheckAnswerIn, Body()],
) -> CheckAnswerOut:
    """Confere uma resposta sem entregar a certa.

    A correção mora aqui, e não no cliente, porque a resposta certa não faz
    parte do contrato de leitura — mandá-la ao navegador para o JavaScript
    comparar seria o mesmo que publicar o gabarito. Na S3 este endpoint passa
    a gravar a tentativa do usuário logado; a resposta que ele devolve não muda.
    """
    exercicio = await _buscar_exercicio(session, exercise_id)
    aceitas = [a.value for a in exercicio.answers]
    return CheckAnswerOut(
        correct=acertou(corpo.answer, aceitas), explanation=exercicio.explanation
    )


@router.get("/exercises/{exercise_id}/answer", response_model=RevealAnswerOut)
async def revelar_resposta(
    exercise_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RevealAnswerOut:
    """Entrega o gabarito — só quando o usuário pede."""
    exercicio = await _buscar_exercicio(session, exercise_id)
    return RevealAnswerOut(
        answers=[a.value for a in exercicio.answers], explanation=exercicio.explanation
    )
