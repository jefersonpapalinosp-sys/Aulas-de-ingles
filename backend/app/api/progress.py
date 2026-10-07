"""Progresso do usuário: aulas estudadas e tentativas de exercício."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.db.models import Exercise, ExerciseAttempt, Lesson, LessonProgress
from app.db.session import get_session
from app.domain.answers import acertou
from app.schemas.progress import (
    AttemptIn,
    AttemptOut,
    LessonProgressOut,
    ProgressOut,
    RevealAnswerOut,
)

router = APIRouter(tags=["progress"])


async def _aula_por_numero(session: AsyncSession, number: int) -> Lesson:
    aula = (
        await session.execute(select(Lesson).where(Lesson.number == number))
    ).scalar_one_or_none()
    if aula is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Aula {number} não existe."
        )
    return aula


async def _exercicio_por_id(session: AsyncSession, exercise_id: int) -> Exercise:
    exercicio = (
        await session.execute(select(Exercise).where(Exercise.id == exercise_id))
    ).scalar_one_or_none()
    if exercicio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Exercício {exercise_id} não existe."
        )
    return exercicio


@router.put("/lessons/{number}/studied", status_code=status.HTTP_204_NO_CONTENT)
async def marcar_estudada(
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Idempotente: marcar duas vezes não cria duas linhas."""
    aula = await _aula_por_numero(session, number)
    ja = (
        await session.execute(
            select(LessonProgress).where(
                LessonProgress.user_id == usuario.id, LessonProgress.lesson_id == aula.id
            )
        )
    ).scalar_one_or_none()
    if ja is None:
        session.add(LessonProgress(user_id=usuario.id, lesson_id=aula.id))
        await session.commit()


@router.delete("/lessons/{number}/studied", status_code=status.HTTP_204_NO_CONTENT)
async def desmarcar_estudada(
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    aula = await _aula_por_numero(session, number)
    await session.execute(
        delete(LessonProgress).where(
            LessonProgress.user_id == usuario.id, LessonProgress.lesson_id == aula.id
        )
    )
    await session.commit()


@router.post("/exercises/{exercise_id}/attempt", response_model=AttemptOut)
async def tentar(
    exercise_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[AttemptIn, Body()],
) -> AttemptOut:
    """Confere a resposta e grava a tentativa.

    A correção acontece aqui porque a resposta certa não faz parte do contrato
    de leitura: mandá-la ao navegador para o JavaScript comparar seria publicar
    o gabarito. A comparação é a mesma de `app/domain/answers.py` — a regra
    mora num lugar só.
    """
    exercicio = await _exercicio_por_id(session, exercise_id)
    certo = acertou(corpo.answer, [a.value for a in exercicio.answers])

    session.add(
        ExerciseAttempt(
            user_id=usuario.id,
            exercise_id=exercicio.id,
            answer=corpo.answer[:200],
            correct=certo,
        )
    )
    await session.commit()
    return AttemptOut(correct=certo, explanation=exercicio.explanation)


@router.get("/exercises/{exercise_id}/answer", response_model=RevealAnswerOut)
async def revelar_resposta(
    exercise_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RevealAnswerOut:
    """Entrega o gabarito — só quando o usuário pede, e só se estiver logado."""
    _ = usuario
    exercicio = await _exercicio_por_id(session, exercise_id)
    return RevealAnswerOut(
        answers=[a.value for a in exercicio.answers], explanation=exercicio.explanation
    )


@router.get("/me/progress", response_model=ProgressOut)
async def meu_progresso(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProgressOut:
    """Uma linha por aula, sempre as dez — aula sem atividade vem zerada."""
    estudadas = {
        p.lesson_id: p.studied_at
        for p in (
            await session.execute(
                select(LessonProgress).where(LessonProgress.user_id == usuario.id)
            )
        ).scalars()
    }

    tentativas = (
        await session.execute(
            select(
                Exercise.lesson_id,
                func.count(ExerciseAttempt.id),
                func.count(ExerciseAttempt.id).filter(ExerciseAttempt.correct),
            )
            .join(Exercise, ExerciseAttempt.exercise_id == Exercise.id)
            .where(ExerciseAttempt.user_id == usuario.id)
            .group_by(Exercise.lesson_id)
        )
    ).all()
    por_aula = {lesson_id: (total, certos) for lesson_id, total, certos in tentativas}

    aulas = list((await session.execute(select(Lesson).order_by(Lesson.number))).scalars())
    linhas = [
        LessonProgressOut(
            lesson_number=a.number,
            studied=a.id in estudadas,
            studied_at=estudadas.get(a.id),
            attempts=por_aula.get(a.id, (0, 0))[0],
            correct=por_aula.get(a.id, (0, 0))[1],
        )
        for a in aulas
    ]
    return ProgressOut(
        studied_count=sum(1 for linha in linhas if linha.studied),
        total_lessons=len(linhas),
        attempts=sum(linha.attempts for linha in linhas),
        correct=sum(linha.correct for linha in linhas),
        lessons=linhas,
    )
