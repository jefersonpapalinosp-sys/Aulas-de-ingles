"""Parceiro de conversa: recorte da aula, roteiro e orquestração de um turno.

Divisão de responsabilidade, que é o que mantém o assistente auditável:

`domain/dialogue.py`
    avalia o turno. Determinístico, sem I/O. É a única coisa que julga o aluno.
`dialogue_prompts.py`
    monta o prompt e **sanea** a resposta do provedor.
`assistance.py`
    fala HTTP com o provedor.
este módulo
    decide a ordem, persiste e escolhe o fallback.

Nenhum texto de turno, transcrição ou resposta do provedor entra em log aqui —
só identificadores e códigos. É requisito do ADR e tem teste próprio.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, raiseload, selectinload

from app.core.config import Settings, get_settings
from app.db.models import (
    DialogueTurn,
    GrammarBlock,
    Lesson,
    LessonMedia,
    SpeakingDialogue,
    TranscriptCue,
    TranscriptionJob,
    User,
)
from app.domain.dialogue import (
    MAX_TURNS_PER_DIALOGUE,
    CheckCode,
    CheckDetails,
    TurnCheck,
    TurnExpectation,
    evaluate,
    evaluation_details,
    failed_codes,
)
from app.domain.enums import TurnInputKind, TurnRole
from app.services import assist_quota, assistance, dialogue_learning, dialogue_prompts
from app.services.dialogue_prompts import LessonBrief, Mode, PartnerTurn

logger = logging.getLogger("app.dialogue")


class DialogueUnavailable(Exception):
    """Modo com IA pedido com a assistência desligada ou sem provedor."""


class TurnLimitReached(Exception):
    """O diálogo chegou ao limite de turnos acordado."""

    def __init__(self, limit: int) -> None:
        super().__init__(limit)
        self.limit = limit


@dataclass(frozen=True)
class TurnOutcome:
    """O que a aplicação precisa saber depois de um turno do aluno.

    `fallback` diz que a resposta veio do roteiro, não do modelo — o aluno
    continua a conversa, e o diálogo guarda o motivo em `error_code`.
    """

    checks: tuple[TurnCheck, ...]
    partner: PartnerTurn
    fallback: bool
    error_code: str | None
    cost_microusd: int
    cost_known: bool
    check_details: CheckDetails | None = None


async def lesson_for_dialogue(session: AsyncSession, lesson_id: int) -> Lesson:
    """Carrega só o recorte editorial permitido ao worker, sem gabaritos."""
    return (
        await session.execute(
            select(Lesson)
            .where(Lesson.id == lesson_id)
            .options(
                raiseload("*"),
                joinedload(Lesson.course),
                selectinload(Lesson.goals),
                selectinload(Lesson.phrases),
                selectinload(Lesson.vocab),
                selectinload(Lesson.grammar_blocks).selectinload(GrammarBlock.rows),
            )
        )
    ).scalar_one()


async def brief_for_lesson(session: AsyncSession, lesson: Lesson) -> LessonBrief:
    """O recorte que o parceiro pode usar, montado das entidades do banco.

    Mesmos campos de `brief_from_seed`, outra fonte: o seed é o arquivo de
    conteúdo e este é o estado publicado. Nada aqui é do aluno — é essa
    propriedade que permite mandar o recorte ao provedor.
    """
    cues = (
        await session.execute(
            select(TranscriptCue.speaker, TranscriptCue.text_en)
            .join(TranscriptCue.media)
            .where(LessonMedia.lesson_id == lesson.id)
            .order_by(LessonMedia.position, TranscriptCue.position)
        )
    ).all()
    script = tuple(
        (cue.speaker.strip(), cue.text_en.strip())
        for cue in cues
        if cue.speaker and cue.speaker.strip() and cue.text_en and cue.text_en.strip()
    )
    grammar_examples = tuple(
        str(row.cells[-1]).strip()
        for block in sorted(lesson.grammar_blocks, key=lambda b: b.position)
        for row in sorted(block.rows, key=lambda r: r.position)
        if row.cells
    )
    return LessonBrief(
        course_slug=lesson.course.slug,
        lesson_number=lesson.number,
        title=lesson.title,
        goals=tuple(goal.text for goal in sorted(lesson.goals, key=lambda g: g.position)),
        focus_points=tuple(lesson.focus_points or ()),
        target_terms=tuple(
            item.term for item in sorted(lesson.vocab, key=lambda v: v.position) if item.term
        ),
        phrases=tuple(
            phrase.text_en for phrase in sorted(lesson.phrases, key=lambda p: p.position)
        ),
        grammar_examples=grammar_examples,
        script=script,
    )


def content_fingerprint(brief: LessonBrief) -> str:
    """Impressão do recorte que o diálogo usou.

    Serve para detectar que a aula mudou debaixo de um diálogo aberto, do mesmo
    jeito que `exercise_fingerprint` faz no laboratório. Só o que o parceiro
    enxerga entra na conta: mudar o título em português não invalida a conversa.
    """
    partes = [
        brief.course_slug,
        str(brief.lesson_number),
        brief.title,
        *brief.goals,
        *brief.focus_points,
        *brief.target_terms,
        *brief.phrases,
        *brief.grammar_examples,
        *(f"{speaker}:{text}" for speaker, text in brief.script),
    ]
    return sha256("␟".join(partes).encode()).hexdigest()


def expectation_for(brief: LessonBrief, position: int) -> TurnExpectation:
    """O que o turno `position` pede do aluno.

    A escolha é determinística e circular: o turno 1 pede o primeiro termo, o
    2 o segundo, e assim por diante. Isso espalha o vocabulário da aula pela
    conversa em vez de cobrar tudo no primeiro turno, e mantém o diálogo
    reproduzível — o mesmo diálogo pede a mesma coisa, o que importa para o
    gate humano do IA-48.

    O padrão gramatical só é cobrado a partir do terceiro turno: os dois
    primeiros existem para a conversa começar.
    """
    terms = brief.target_terms
    patterns = brief.grammar_examples
    termo = (terms[(position - 1) % len(terms)],) if terms else ()
    padrao = (patterns[(position - 1) % len(patterns)],) if patterns and position >= 3 else ()
    return TurnExpectation(target_terms=termo, grammar_patterns=padrao)


def script_fallback(brief: LessonBrief, dialogue: SpeakingDialogue, position: int) -> PartnerTurn:
    """Próximo turno vindo do roteiro da aula, sem IA.

    É a rede do modo Guiado quando o provedor falha e é o próprio modo Roteiro.
    Sem dica: dica é coisa que o modelo escreve, e aqui ele não falou.
    """
    turns = dialogue_prompts.script_turns(brief, dialogue.partner_speaker)
    partner_lines = [turn["text_en"] for turn in turns if turn["role"] in ("partner", "repeat")]
    if not partner_lines:
        return PartnerTurn(partner_text="Let's keep practising.", hints=(), confidence=0.0)
    return PartnerTurn(
        partner_text=partner_lines[(position - 1) % len(partner_lines)],
        hints=(),
        confidence=0.0,
    )


def _history(turns: list[DialogueTurn]) -> tuple[tuple[TurnRole, str], ...]:
    """Histórico em texto, do mais antigo ao mais novo, só com o que existe."""
    return tuple(
        ("student" if turn.role == "student" else "partner", texto)
        for turn in sorted(turns, key=lambda t: t.position)
        if (texto := turn.transcript if turn.role == "student" else turn.partner_text)
    )


def _provider_turn(
    settings: Settings,
    brief: LessonBrief,
    mode: Mode,
    transcript: str,
    codes: tuple[CheckCode, ...],
    history: tuple[tuple[TurnRole, str], ...],
    requested_terms: tuple[str, ...],
    idempotency_key: str,
) -> tuple[PartnerTurn | None, int, bool, str | None]:
    """Chama o provedor e saneia. Devolve `(turno, custo, custo_conhecido, erro)`.

    Erro aqui nunca interrompe o diálogo: quem chama decide o fallback. Os
    códigos de erro são os mesmos do resto da assistência, para o painel não
    precisar de um vocabulário novo.
    """
    messages = dialogue_prompts.turn_messages(
        brief, mode, transcript, codes, history, requested_terms
    )
    schema = dialogue_prompts.response_schema(codes)
    try:
        if settings.assist_provider_kind == "ollama":
            result = assistance.call_ollama_dialogue_provider(
                settings.assist_ollama_base_url,
                settings.assist_ollama_dialogue_model,
                messages,
                schema,
                timeout=settings.assist_timeout_seconds,
            )
        else:
            url = settings.assist_dialogue_url
            if not url:
                raise assistance.ProviderFailure("provider_unavailable")
            result = assistance.call_dialogue_provider(
                url,
                messages,
                schema,
                token=settings.assist_provider_token,
                timeout=settings.assist_timeout_seconds,
                idempotency_key=idempotency_key,
            )
    except assistance.ProviderFailure as error:
        return None, 0, False, error.code
    except Exception:
        # Falha inesperada do gateway não vaza mensagem nem derruba o turno.
        return None, 0, False, "internal_provider_error"
    partner = dialogue_prompts.sanitize_provider_output(result.raw, codes)
    if partner is None:
        # A resposta veio, mas inventou código, URL ou e-mail: descartada. O
        # custo já aconteceu e é registrado de todo jeito.
        return None, result.cost_microusd, result.cost_known, "invalid_provider_response"
    return partner, result.cost_microusd, result.cost_known, None


async def partner_reply(
    session: AsyncSession,
    dialogue: SpeakingDialogue,
    brief: LessonBrief,
    position: int,
    transcript: str,
    *,
    idempotency_key: str,
    allow_provider: bool = True,
) -> TurnOutcome:
    """Avalia a fala do aluno e produz o turno do parceiro.

    A ordem é deliberada: avaliar primeiro, chamar o provedor depois. A
    avaliação não depende de rede, então o aluno sempre recebe o resultado
    determinístico — mesmo que o modelo não responda. E o provedor só recebe os
    códigos reprovados, nunca a avaliação inteira.

    **Não mexe em cota.** O contrato do IA-45 devolve `202 + job_id`, então o
    provedor é chamado no worker: a reserva acontece na admissão do turno (onde
    o 429 da cota tem de aparecer, antes de qualquer rede) e o consumo no
    despacho, como a fila de transcrição já faz. Reservar aqui seria cobrar na
    hora errada e duas vezes.
    """
    settings = get_settings()
    expectation = expectation_for(brief, position)
    checks = evaluate(transcript, expectation)
    details = evaluation_details(transcript, expectation)
    codes = failed_codes(checks)

    turns = list(
        (
            await session.execute(
                select(DialogueTurn).where(DialogueTurn.dialogue_id == dialogue.id)
            )
        ).scalars()
    )
    history = _history(turns)

    usar_modelo = (
        allow_provider
        and dialogue.mode != "script"
        and settings.assisted_features_enabled
        and settings.dialogue_assist_configured
        and settings.dialogue_account_allowed(dialogue.user_id)
    )
    if not usar_modelo:
        motivo = None if dialogue.mode == "script" else "assist_disabled"
        return TurnOutcome(
            checks=checks,
            check_details=details,
            partner=script_fallback(brief, dialogue, position),
            fallback=dialogue.mode != "script",
            error_code=motivo,
            cost_microusd=0,
            cost_known=True,
        )

    partner, custo, custo_conhecido, erro = _provider_turn(
        settings,
        brief,
        dialogue.mode,
        transcript,
        codes,
        history,
        expectation.target_terms,
        idempotency_key,
    )
    if partner is None:
        logger.info(
            "dialogue_turn_fallback",
            extra={"dialogue_id": dialogue.id, "position": position, "error_code": erro},
        )
        return TurnOutcome(
            checks=checks,
            check_details=details,
            partner=script_fallback(brief, dialogue, position),
            fallback=True,
            error_code=erro,
            cost_microusd=custo,
            cost_known=custo_conhecido,
        )
    return TurnOutcome(
        checks=checks,
        check_details=details,
        partner=partner,
        fallback=False,
        error_code=None,
        cost_microusd=custo,
        cost_known=custo_conhecido,
    )


async def create_dialogue(
    session: AsyncSession,
    usuario: User,
    lesson: Lesson,
    *,
    mode: Mode,
    operation_key: str,
    partner_speaker: str | None = None,
) -> tuple[SpeakingDialogue, LessonBrief]:
    """Abre um diálogo, ou devolve o que a mesma `operation_key` já abriu.

    Os modos com IA são recusados quando a assistência está desligada: o aluno
    recebe `DialogueUnavailable` e a interface oferece o Roteiro, que funciona
    sem provedor nenhum.
    """
    await assist_quota.lock_user(session, usuario.id)
    settings = get_settings()
    if mode != "script" and not (
        settings.assisted_features_enabled
        and settings.dialogue_assist_configured
        and settings.dialogue_account_allowed(usuario.id)
    ):
        raise DialogueUnavailable(mode)

    brief = await brief_for_lesson(session, lesson)
    existing = (
        await session.execute(
            select(SpeakingDialogue).where(
                SpeakingDialogue.user_id == usuario.id,
                SpeakingDialogue.operation_key == operation_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.lesson_id != lesson.id or existing.mode != mode:
            raise HTTPException(409, "Chave de diálogo já utilizada com outra aula ou modo.")
        return existing, brief

    falantes = tuple(dict.fromkeys(speaker for speaker, _ in brief.script))
    dialogue = SpeakingDialogue(
        user_id=usuario.id,
        lesson_id=lesson.id,
        operation_key=operation_key,
        mode=mode,
        state="active",
        partner_speaker=(
            partner_speaker if partner_speaker in falantes else (falantes[0] if falantes else None)
        ),
        content_version=lesson.id,
        content_fingerprint=content_fingerprint(brief),
        provider_name=settings.assist_provider_name if mode != "script" else None,
        rubric_version=dialogue_prompts.PROMPT_VERSION,
        turn_limit=MAX_TURNS_PER_DIALOGUE,
        started_at=datetime.now(UTC),
    )
    session.add(dialogue)
    await session.flush()
    logger.info("dialogue_created", extra={"dialogue_id": dialogue.id, "mode": mode})
    return dialogue, brief


async def admit_turn(
    session: AsyncSession,
    dialogue: SpeakingDialogue,
    position: int,
    *,
    input_kind: TurnInputKind,
    idempotency_key: str,
    transcript: str | None = None,
    speaking_attempt_id: int | None = None,
) -> tuple[DialogueTurn, TranscriptionJob | None]:
    """Admite o turno do aluno: grava, reserva cota e enfileira o trabalho.

    É aqui que o 429 da cota tem de aparecer — antes de qualquer rede, com o
    aluno ainda na requisição. Não há fallback automático para o Roteiro:
    gastar o turno numa resposta de roteiro sem ele pedir esconderia o fim da
    cota, e quem decide continuar no Roteiro é ele.

    Idempotência por `(dialogue_id, position)`: reenviar o mesmo turno devolve
    o que já foi admitido, sem segunda cobrança nem segundo job.
    """
    if dialogue.mode != "script" and not get_settings().dialogue_account_allowed(dialogue.user_id):
        raise DialogueUnavailable(dialogue.mode)
    existing = (
        await session.execute(
            select(DialogueTurn).where(
                DialogueTurn.dialogue_id == dialogue.id,
                DialogueTurn.position == position,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        job = (
            (
                await session.execute(
                    select(TranscriptionJob).where(
                        TranscriptionJob.id == existing.transcription_job_id
                    )
                )
            ).scalar_one_or_none()
            if existing.transcription_job_id
            else None
        )
        return existing, job

    if position < 1:
        raise HTTPException(422, "Posição de turno inválida.")
    if position > dialogue.turn_limit:
        raise TurnLimitReached(dialogue.turn_limit)

    turn = DialogueTurn(
        dialogue_id=dialogue.id,
        user_id=dialogue.user_id,
        position=position,
        role="student",
        input_kind=input_kind,
        speaking_attempt_id=speaking_attempt_id,
        state="pending",
        transcript=transcript,
        expires_at=turn_expiry(),
    )
    # Roteiro não tem provedor nem custo: resolve na hora. Depender do worker
    # para um modo que não chama ninguém tiraria do ar justamente o modo que
    # deveria funcionar quando o resto está fora.
    if dialogue.mode == "script":
        lesson = (
            await session.execute(select(Lesson).where(Lesson.id == dialogue.lesson_id))
        ).scalar_one()
        brief = await brief_for_lesson(session, lesson)
        outcome = await partner_reply(
            session, dialogue, brief, position, transcript or "", idempotency_key=idempotency_key
        )
        # O runtime pode INSERT, mas não UPDATE de resultado: o Roteiro nasce
        # concluído. O Guiado continua sendo preenchido somente pelo worker.
        _apply_outcome(turn, dialogue, outcome, transcript or "")
        session.add(turn)
        await session.flush()
        await dialogue_learning.record_learning(session, dialogue, turn)
        return turn, None

    reservation, admitida = await assist_quota.reserve(
        session,
        dialogue.user_id,
        idempotency_key,
        # Vincula a chave ao diálogo e à posição, mesmo em aulas idênticas.
        sha256(f"{dialogue.id}:{dialogue.content_fingerprint}:{position}".encode()).hexdigest(),
        assist_quota.DIALOGUE_MODALITY,
    )
    if not admitida:
        raise HTTPException(409, "Chave de turno já utilizada. Reenvie a entrada original.")
    settings = get_settings()
    agora = datetime.now(UTC)
    job = TranscriptionJob(
        assist_reservation_id=reservation.id,
        user_id=dialogue.user_id,
        speaking_attempt_id=speaking_attempt_id,
        kind="dialogue",
        provider=settings.assist_provider_name,
        status="queued",
        idempotency_key=reservation.provider_key,
        max_attempts=settings.assist_job_max_attempts,
        next_attempt_at=agora,
        expires_at=agora + timedelta(days=settings.assist_retention_days),
    )
    session.add(job)
    await session.flush()
    turn.transcription_job_id = job.id
    session.add(turn)
    await session.flush()
    logger.info(
        "dialogue_turn_admitted",
        extra={"dialogue_id": dialogue.id, "position": position, "job_id": job.id},
    )
    return turn, job


async def resolve_turn(
    session: AsyncSession,
    turn: DialogueTurn,
    dialogue: SpeakingDialogue,
    brief: LessonBrief,
    transcript: str,
) -> TurnOutcome:
    """Fecha o turno com o resultado: checks, resposta do parceiro e estado.

    Chamada pelo worker depois do despacho autorizado (cota já consumida) ou,
    no Roteiro, pela própria rota. O turno sai de `pending` com tudo gravado —
    é o `GET` do diálogo que o cliente consulta depois.
    """
    # Ordem única também para o worker: dois turnos do mesmo diálogo não
    # podem observar contagens diferentes ao criar a revisão recorrente.
    await session.execute(
        select(SpeakingDialogue.id).where(SpeakingDialogue.id == dialogue.id).with_for_update()
    )
    await session.refresh(turn)
    if turn.state == "completed":
        # Reentrega do job não chama o provedor nem cobra novamente. Checks
        # persistidos bastam para devolver o resultado anterior.
        return TurnOutcome(
            check_details=turn.check_details,
            checks=tuple(
                TurnCheck(code, bool(turn.checks[code]), "")
                for code in dialogue_prompts.CHECK_CODES
                if code in turn.checks
            ),
            partner=PartnerTurn(
                partner_text=turn.partner_text or "",
                hints=tuple(
                    dialogue_prompts.Hint(code=code, message=hint["message"])
                    for hint in turn.hints
                    for code in dialogue_prompts.CHECK_CODES
                    if code == hint["code"]
                ),
                confidence=turn.confidence or 0.0,
            ),
            fallback=turn.fallback,
            error_code=turn.error_code,
            cost_microusd=0,
            cost_known=True,
        )
    outcome = await partner_reply(
        session,
        dialogue,
        brief,
        turn.position,
        transcript,
        idempotency_key=f"turn-{turn.id}",
    )
    _apply_outcome(turn, dialogue, outcome, transcript)
    await session.flush()
    await dialogue_learning.record_learning(session, dialogue, turn)
    return outcome


def _apply_outcome(
    turn: DialogueTurn, dialogue: SpeakingDialogue, outcome: TurnOutcome, transcript: str
) -> None:
    turn.transcript = transcript
    turn.checks = {check.code: check.passed for check in outcome.checks}
    turn.check_details = outcome.check_details
    turn.partner_text = outcome.partner.partner_text
    turn.hints = [{"code": hint.code, "message": hint.message} for hint in outcome.partner.hints]
    turn.confidence = outcome.partner.confidence
    turn.fallback = outcome.fallback
    turn.error_code = outcome.error_code
    turn.cost_microusd = outcome.cost_microusd
    turn.state = "completed"
    turn.completed_at = datetime.now(UTC)
    if position_is_last(dialogue, turn.position):
        dialogue.state = "completed"
        dialogue.ended_at = turn.completed_at


def position_is_last(dialogue: SpeakingDialogue, position: int) -> bool:
    """O turno que fecha o diálogo pelo limite acordado."""
    return position >= dialogue.turn_limit


def turn_expiry(settings: Settings | None = None) -> datetime:
    """Quando `transcript`, `partner_text` e `hints` deixam de ser consultáveis."""
    retention = (settings or get_settings()).assist_retention_days
    return datetime.now(UTC) + timedelta(days=retention)
