"""Progresso do usuário: aulas estudadas e tentativas de exercício."""

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UsuarioAtual
from app.api.review import adicionar_cartas, adicionar_item_revisao
from app.db.models import (
    Course,
    CourseUnit,
    Exercise,
    ExerciseAttempt,
    ExerciseHint,
    Lesson,
    LessonProgress,
    PracticeSession,
    PracticeSessionItem,
    ReviewItem,
    SkillEvidence,
    StepProgress,
    StudySessionProgress,
    User,
    VocabItem,
)
from app.db.session import get_session
from app.domain.answers import (
    analisar_resposta,
    normalizar,
    validar_e_canonicalizar_classificacao,
)
from app.schemas.progress import (
    STUDY_STEPS,
    AttemptFeedbackOut,
    AttemptIn,
    AttemptOut,
    ExerciseHintOut,
    FeedbackTokenOut,
    LessonProgressOut,
    ProgressOut,
    RevealAnswerOut,
    StudySessionIn,
    StudySessionOut,
    StudyStep,
)
from app.services.curriculum import DEFAULT_COURSE_SLUG, lesson_by_course_number
from app.services.practice import (
    complete_session_if_ready,
    ensure_session_content_current,
    ensure_session_mutable,
    get_owned_practice_session,
    get_practice_item,
    practice_attempt_state,
)

router = APIRouter(tags=["progress"])


async def _aula_por_numero(
    session: AsyncSession, number: int, course_slug: str = DEFAULT_COURSE_SLUG
) -> Lesson:
    aula = await lesson_by_course_number(session, course_slug, number)
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


def _attempt_out(
    attempt: ExerciseAttempt,
    exercise: Exercise,
    practice: PracticeSession | None = None,
    item: PracticeSessionItem | None = None,
) -> AttemptOut:
    feedback = analisar_resposta(attempt.answer, [answer.value for answer in exercise.answers])
    return AttemptOut(
        attempt_id=attempt.id,
        correct=attempt.correct,
        explanation=exercise.explanation if attempt.correct else None,
        feedback=AttemptFeedbackOut(
            category=feedback.category,
            message=feedback.message,
            tokens=[
                FeedbackTokenOut(text=token.text, status=token.status) for token in feedback.tokens
            ],
        ),
        session=(
            practice_attempt_state(practice, item)
            if practice is not None and item is not None
            else None
        ),
    )


async def _marcar_estudada(
    number: int,
    course_slug: str,
    usuario: UsuarioAtual,
    session: AsyncSession,
) -> None:
    """Marca a aula e põe o vocabulário dela no deck de revisão.

    Idempotente nas duas pontas: marcar duas vezes não cria duas linhas nem
    reinicia o agendamento de cartas que já existem.
    """
    aula = await _aula_por_numero(session, number, course_slug)
    ja = (
        await session.execute(
            select(LessonProgress).where(
                LessonProgress.user_id == usuario.id, LessonProgress.lesson_id == aula.id
            )
        )
    ).scalar_one_or_none()
    if ja is None:
        session.add(LessonProgress(user_id=usuario.id, lesson_id=aula.id))
    await adicionar_cartas(session, usuario, list(aula.vocab))
    await session.commit()


@router.put("/lessons/{number}/studied", status_code=status.HTTP_204_NO_CONTENT)
async def marcar_estudada(
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await _marcar_estudada(number, DEFAULT_COURSE_SLUG, usuario, session)


@router.put(
    "/courses/{course_slug}/lessons/{number}/studied",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def marcar_estudada_no_curso(
    course_slug: str,
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await _marcar_estudada(number, course_slug, usuario, session)


async def _desmarcar_estudada(
    number: int,
    course_slug: str,
    usuario: UsuarioAtual,
    session: AsyncSession,
) -> None:
    aula = await _aula_por_numero(session, number, course_slug)
    await session.execute(
        delete(LessonProgress).where(
            LessonProgress.user_id == usuario.id, LessonProgress.lesson_id == aula.id
        )
    )
    await session.commit()


@router.delete("/lessons/{number}/studied", status_code=status.HTTP_204_NO_CONTENT)
async def desmarcar_estudada(
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await _desmarcar_estudada(number, DEFAULT_COURSE_SLUG, usuario, session)


@router.delete(
    "/courses/{course_slug}/lessons/{number}/studied",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def desmarcar_estudada_no_curso(
    course_slug: str,
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await _desmarcar_estudada(number, course_slug, usuario, session)


async def _obter_sessao_de_estudo(
    number: int,
    course_slug: str,
    usuario: UsuarioAtual,
    session: AsyncSession,
) -> StudySessionOut:
    """Devolve o ponto salvo ou o início da jornada quando ela ainda não existe."""
    aula = await _aula_por_numero(session, number, course_slug)
    progresso = (
        await session.execute(
            select(StudySessionProgress).where(
                StudySessionProgress.user_id == usuario.id,
                StudySessionProgress.lesson_id == aula.id,
            )
        )
    ).scalar_one_or_none()
    if progresso is None:
        return StudySessionOut(
            lesson_number=number,
            current_step="preparar",
            completed_steps=[],
            started_at=None,
            updated_at=None,
            completed_at=None,
            total_seconds=0,
        )
    return StudySessionOut(
        lesson_number=number,
        current_step=cast(StudyStep, progresso.current_step),
        completed_steps=cast(list[StudyStep], progresso.completed_steps),
        started_at=progresso.started_at,
        updated_at=progresso.updated_at,
        completed_at=progresso.completed_at,
        total_seconds=progresso.total_seconds,
    )


@router.get("/lessons/{number}/study-session", response_model=StudySessionOut)
async def obter_sessao_de_estudo(
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> StudySessionOut:
    response.headers["Cache-Control"] = "private, no-store"
    return await _obter_sessao_de_estudo(number, DEFAULT_COURSE_SLUG, usuario, session)


@router.get(
    "/courses/{course_slug}/lessons/{number}/study-session",
    response_model=StudySessionOut,
)
async def obter_sessao_de_estudo_no_curso(
    course_slug: str,
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> StudySessionOut:
    response.headers["Cache-Control"] = "private, no-store"
    return await _obter_sessao_de_estudo(number, course_slug, usuario, session)


async def _salvar_sessao_de_estudo(
    number: int,
    course_slug: str,
    usuario: UsuarioAtual,
    session: AsyncSession,
    corpo: Annotated[StudySessionIn, Body()],
) -> StudySessionOut:
    """Cria ou atualiza a retomada da jornada, isolada por conta e aula."""
    aula = await _aula_por_numero(session, number, course_slug)
    progresso = (
        await session.execute(
            select(StudySessionProgress).where(
                StudySessionProgress.user_id == usuario.id,
                StudySessionProgress.lesson_id == aula.id,
            )
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if progresso is None:
        progresso = StudySessionProgress(
            user_id=usuario.id,
            lesson_id=aula.id,
            current_step=corpo.current_step,
            completed_steps=list(corpo.completed_steps),
        )
        session.add(progresso)
        await session.flush()
    else:
        # A sessão é salva ao entrar e ao trocar de etapa. O intervalo entre
        # esses eventos é uma aproximação útil do tempo ativo; o teto impede
        # que uma aba esquecida aberta infle a métrica.
        elapsed = min(30 * 60, max(0, int((now - progresso.updated_at).total_seconds())))
        if elapsed:
            previous_step = (
                await session.execute(
                    select(StepProgress).where(
                        StepProgress.study_session_id == progresso.id,
                        StepProgress.step == progresso.current_step,
                    )
                )
            ).scalar_one_or_none()
            if previous_step is None:
                previous_step = StepProgress(
                    study_session_id=progresso.id,
                    step=progresso.current_step,
                )
                session.add(previous_step)
            previous_step.seconds_spent += elapsed
            progresso.total_seconds += elapsed

    progresso.current_step = corpo.current_step
    progresso.completed_steps = list(corpo.completed_steps)
    progresso.updated_at = now
    if len(corpo.completed_steps) == len(STUDY_STEPS):
        progresso.completed_at = progresso.completed_at or now

    existing_steps = {
        item.step: item
        for item in (
            await session.execute(
                select(StepProgress).where(StepProgress.study_session_id == progresso.id)
            )
        ).scalars()
    }
    for step in {corpo.current_step, *corpo.completed_steps}:
        step_progress = existing_steps.get(step)
        if step_progress is None:
            step_progress = StepProgress(study_session_id=progresso.id, step=step)
            session.add(step_progress)
            existing_steps[step] = step_progress
        if step in corpo.completed_steps and step_progress.completed_at is None:
            step_progress.completed_at = now
    await session.commit()
    await session.refresh(progresso)
    return StudySessionOut(
        lesson_number=number,
        current_step=corpo.current_step,
        completed_steps=corpo.completed_steps,
        started_at=progresso.started_at,
        updated_at=progresso.updated_at,
        completed_at=progresso.completed_at,
        total_seconds=progresso.total_seconds,
    )


@router.put("/lessons/{number}/study-session", response_model=StudySessionOut)
async def salvar_sessao_de_estudo(
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[StudySessionIn, Body()],
) -> StudySessionOut:
    return await _salvar_sessao_de_estudo(number, DEFAULT_COURSE_SLUG, usuario, session, corpo)


@router.put(
    "/courses/{course_slug}/lessons/{number}/study-session",
    response_model=StudySessionOut,
)
async def salvar_sessao_de_estudo_no_curso(
    course_slug: str,
    number: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[StudySessionIn, Body()],
) -> StudySessionOut:
    return await _salvar_sessao_de_estudo(number, course_slug, usuario, session, corpo)


@router.post("/exercises/{exercise_id}/attempt", response_model=AttemptOut)
async def tentar(
    exercise_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    corpo: Annotated[AttemptIn, Body()],
    response: Response,
) -> AttemptOut:
    """Confere a resposta e grava a tentativa.

    A correção acontece aqui porque a resposta certa não faz parte do contrato
    de leitura: mandá-la ao navegador para o JavaScript comparar seria publicar
    o gabarito. A comparação é a mesma de `app/domain/answers.py` — a regra
    mora num lugar só.
    """
    response.headers["Cache-Control"] = "private, no-store"
    exercicio = await _exercicio_por_id(session, exercise_id)
    answer = corpo.answer
    if exercicio.activity_type == "classification":
        try:
            answer = validar_e_canonicalizar_classificacao(
                answer,
                exercicio.classification_items or [],
                exercicio.classification_categories or [],
            )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
    key = str(corpo.idempotency_key)
    practice: PracticeSession | None = None
    practice_item: PracticeSessionItem | None = None
    if corpo.practice_session_id is not None:
        practice = await get_owned_practice_session(
            session,
            corpo.practice_session_id,
            usuario.id,
            for_update=True,
        )
        practice_item = get_practice_item(practice, exercicio.id)

    # Em tentativas ligadas ao laboratório, a consulta acontece depois do
    # lock. Assim, duas requisições simultâneas com a mesma chave também são
    # idempotentes quando a primeira delas acaba de concluir a sessão.
    existente = (
        await session.execute(
            select(ExerciseAttempt).where(
                ExerciseAttempt.user_id == usuario.id,
                ExerciseAttempt.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()
    if existente is not None:
        requested_item_id = practice_item.id if practice_item is not None else None
        if (
            existente.exercise_id != exercicio.id
            or existente.answer != answer
            or existente.practice_session_item_id != requested_item_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A chave de idempotência já foi usada em outra tentativa.",
            )
        if practice is not None and practice_item is not None:
            ensure_session_content_current(practice)
            # As entidades podem ter sido carregadas antes de a aba vencedora
            # confirmar a transação; atualize os contadores antes de responder.
            await session.refresh(practice_item)
            await session.refresh(practice)
        return _attempt_out(existente, exercicio, practice, practice_item)

    if practice is not None:
        ensure_session_mutable(practice)

    feedback = analisar_resposta(answer, [a.value for a in exercicio.answers])
    certo = feedback.category == "correct"

    attempt_id = (
        await session.execute(
            insert(ExerciseAttempt)
            .values(
                user_id=usuario.id,
                exercise_id=exercicio.id,
                practice_session_item_id=(practice_item.id if practice_item is not None else None),
                idempotency_key=key,
                answer=answer,
                correct=certo,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
            .returning(ExerciseAttempt.id)
        )
    ).scalar_one_or_none()
    if attempt_id is None:
        # Outra aba ou a fila offline gravou a mesma tentativa enquanto esta
        # requisição aguardava o banco. O vencedor é a resposta idempotente.
        existente = (
            await session.execute(
                select(ExerciseAttempt).where(
                    ExerciseAttempt.user_id == usuario.id,
                    ExerciseAttempt.idempotency_key == key,
                )
            )
        ).scalar_one()
        if corpo.practice_session_id is not None:
            practice = await get_owned_practice_session(
                session,
                corpo.practice_session_id,
                usuario.id,
                for_update=True,
            )
            practice_item = get_practice_item(practice, exercicio.id)
        requested_item_id = practice_item.id if practice_item is not None else None
        if (
            existente.exercise_id != exercicio.id
            or existente.answer != answer
            or existente.practice_session_item_id != requested_item_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A chave de idempotência já foi usada em outra tentativa.",
            )
        if practice is not None and practice_item is not None:
            ensure_session_content_current(practice)
            await session.refresh(practice_item)
            await session.refresh(practice)
        return _attempt_out(existente, exercicio, practice, practice_item)
    tentativa = (
        await session.execute(select(ExerciseAttempt).where(ExerciseAttempt.id == attempt_id))
    ).scalar_one()

    if practice is not None and practice_item is not None:
        practice_item.attempt_count += 1
        if practice_item.first_try_correct is None:
            practice_item.first_try_correct = certo
        if certo and practice_item.completed_at is None:
            practice_item.completed_at = datetime.now(UTC)
        practice.updated_at = datetime.now(UTC)
        complete_session_if_ready(practice)
    session.add(
        SkillEvidence(
            user_id=usuario.id,
            skill=exercicio.skill,
            source_type="exercise_attempt",
            source_id=tentativa.id,
            score=1.0 if certo else 0.0,
        )
    )
    if not certo:
        matched_vocab = await _cartas_do_erro(session, usuario, exercicio)
        if not matched_vocab:
            await adicionar_item_revisao(
                session,
                usuario,
                lesson_id=exercicio.lesson_id,
                item_type="listening" if exercicio.skill == "listening" else "grammar_error",
                source_type="exercise",
                source_id=exercicio.id,
                source_key=f"exercise:{exercicio.id}",
                skill=exercicio.skill,
                prompt=exercicio.prompt,
                prompt_note=f"Sua última resposta: {answer[:120]}",
                answer=" / ".join(answer.value for answer in exercicio.answers),
                context=exercicio.explanation,
                origin_reason="Este exercício voltou porque houve uma resposta incorreta.",
                estimated_seconds=120 if exercicio.skill == "listening" else 75,
            )
    await session.commit()
    await session.refresh(tentativa)
    return _attempt_out(tentativa, exercicio, practice, practice_item)


@router.get("/exercises/{exercise_id}/hints/{level}", response_model=ExerciseHintOut)
async def obter_dica(
    exercise_id: int,
    level: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> ExerciseHintOut:
    """Libera dicas em ordem; a segunda exige ao menos uma tentativa errada."""
    response.headers["Cache-Control"] = "private, no-store"
    exercise = await _exercicio_por_id(session, exercise_id)
    hint = (
        await session.execute(
            select(ExerciseHint).where(
                ExerciseHint.exercise_id == exercise.id, ExerciseHint.level == level
            )
        )
    ).scalar_one_or_none()
    if hint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dica não existe.")
    if level > 1:
        wrong_attempts = (
            await session.execute(
                select(func.count())
                .select_from(ExerciseAttempt)
                .where(
                    ExerciseAttempt.user_id == usuario.id,
                    ExerciseAttempt.exercise_id == exercise.id,
                    ExerciseAttempt.correct.is_(False),
                )
            )
        ).scalar_one()
        if wrong_attempts == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Faça uma tentativa antes de abrir esta dica.",
            )
    return ExerciseHintOut(level=hint.level, content=hint.content)


async def _cartas_do_erro(session: AsyncSession, usuario: User, exercicio: Exercise) -> bool:
    """Errar um exercício põe no deck o item de vocabulário que ele cobra.

    Vale para a minoria de exercícios cuja resposta certa é, literalmente, um
    termo do vocabulário da aula; a maior parte treina gramática, não palavra.
    Quando não casa, nada acontece: o grosso do deck vem de marcar a aula como
    estudada.
    """
    aceitas = {normalizar(a.value) for a in exercicio.answers}
    itens = list(
        (
            await session.execute(
                select(VocabItem).where(VocabItem.lesson_id == exercicio.lesson_id)
            )
        ).scalars()
    )
    casando = [
        item
        for item in itens
        if normalizar(item.term) in aceitas
        or any(normalizar(parte) in aceitas for parte in item.term.split("/"))
    ]
    await adicionar_cartas(session, usuario, casando)
    return bool(casando)


@router.get("/exercises/{exercise_id}/answer", response_model=RevealAnswerOut)
async def revelar_resposta(
    exercise_id: int,
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
) -> RevealAnswerOut:
    """Entrega o gabarito — só quando o usuário pede, e só se estiver logado."""
    response.headers["Cache-Control"] = "private, no-store"
    _ = usuario
    exercicio = await _exercicio_por_id(session, exercise_id)
    return RevealAnswerOut(
        answers=[a.value for a in exercicio.answers], explanation=exercicio.explanation
    )


@router.get("/me/progress", response_model=ProgressOut)
async def meu_progresso(
    usuario: UsuarioAtual,
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    course: Annotated[
        str | None,
        Query(description="Limita aulas e denominadores ao slug de um curso."),
    ] = None,
    unit: Annotated[
        str | None,
        Query(description="Limita aulas, tentativas e revisões a uma unidade."),
    ] = None,
) -> ProgressOut:
    """Uma linha por aula publicada, opcionalmente limitada a curso e unidade."""
    response.headers["Cache-Control"] = "private, no-store"
    if unit is not None and course is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="O parâmetro course é obrigatório quando unit é informado.",
        )

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

    lessons_stmt = (
        select(Lesson)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            Course.status == "published",
            CourseUnit.status == "published",
        )
        .order_by(Course.position, CourseUnit.position, Lesson.position)
    )
    if course is not None:
        lessons_stmt = lessons_stmt.where(Course.slug == course)
    if unit is not None:
        lessons_stmt = lessons_stmt.where(CourseUnit.slug == unit)
    aulas = list((await session.execute(lessons_stmt)).scalars())
    linhas = [
        LessonProgressOut(
            course_slug=a.course_slug,
            unit_slug=a.unit_slug,
            lesson_number=a.number,
            studied=a.id in estudadas,
            studied_at=estudadas.get(a.id),
            attempts=por_aula.get(a.id, (0, 0))[0],
            correct=por_aula.get(a.id, (0, 0))[1],
        )
        for a in aulas
    ]
    cards_stmt = (
        select(func.count())
        .select_from(ReviewItem)
        .join(Lesson, ReviewItem.lesson_id == Lesson.id)
        .join(Course, Lesson.course_id == Course.id)
        .join(CourseUnit, Lesson.unit_id == CourseUnit.id)
        .where(
            ReviewItem.user_id == usuario.id,
            Course.status == "published",
            CourseUnit.status == "published",
        )
    )
    if course is not None:
        cards_stmt = cards_stmt.where(Course.slug == course)
    if unit is not None:
        cards_stmt = cards_stmt.where(CourseUnit.slug == unit)
    total_cartas = (await session.execute(cards_stmt)).scalar_one()
    vencidas = (
        await session.execute(
            cards_stmt.where(
                ReviewItem.status == "active",
                ReviewItem.due_at <= datetime.now(UTC),
            )
        )
    ).scalar_one()

    return ProgressOut(
        review_due=vencidas,
        review_cards=total_cartas,
        studied_count=sum(1 for linha in linhas if linha.studied),
        total_lessons=len(linhas),
        attempts=sum(linha.attempts for linha in linhas),
        correct=sum(linha.correct for linha in linhas),
        lessons=linhas,
    )
