"""Serviço do parceiro de conversa: recorte, impressão, expectativa e fallback.

Os critérios de aceite do BE-46 que dependem só do serviço estão aqui: modo
Roteiro completo sem provedor, fallback no meio do diálogo sem perder turnos
anteriores, e resposta inventada descartada. Cota e rotas têm testes próprios.
"""

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import DialogueTurn, Lesson, SpeakingDialogue, User
from app.services import assistance, dialogue, dialogue_prompts


async def _lesson(session: AsyncSession, number: int = 31) -> Lesson:
    return (
        await session.execute(select(Lesson).where(Lesson.number == number).limit(1))
    ).scalar_one()


async def _conta(session: AsyncSession, email: str) -> User:
    user = User(email=email, password_hash="x", display_name="Dialogo")
    session.add(user)
    await session.flush()
    return user


async def _brief(session: AsyncSession, number: int = 31) -> dialogue_prompts.LessonBrief:
    return await dialogue.brief_for_lesson(session, await _lesson(session, number))


@pytest.mark.asyncio
async def test_recorte_vem_do_banco_com_os_campos_que_o_parceiro_usa(
    session: AsyncSession,
) -> None:
    brief = await _brief(session)
    assert brief.course_slug and brief.lesson_number == 31
    assert brief.title and brief.goals and brief.target_terms
    # O roteiro sai dos `transcript_cue`, com falante e fala.
    assert brief.script and all(speaker and texto for speaker, texto in brief.script)
    # Nada do aluno entra no recorte: é isso que permite mandá-lo ao provedor.
    serializado = json.dumps(asdict(brief), default=list)
    assert "@" not in serializado


@pytest.mark.asyncio
async def test_impressao_muda_com_o_conteudo_e_nao_com_o_resto(
    session: AsyncSession,
) -> None:
    lesson = await _lesson(session)
    antes = dialogue.content_fingerprint(await dialogue.brief_for_lesson(session, lesson))
    assert antes == dialogue.content_fingerprint(await dialogue.brief_for_lesson(session, lesson))

    # Título em português não é visto pelo parceiro: não invalida a conversa.
    lesson.title_pt = "Outro título em português"
    await session.flush()
    assert dialogue.content_fingerprint(await dialogue.brief_for_lesson(session, lesson)) == antes

    # O título em inglês é parte do recorte: muda a impressão.
    lesson.title = "A different English title"
    await session.flush()
    assert dialogue.content_fingerprint(await dialogue.brief_for_lesson(session, lesson)) != antes


@pytest.mark.asyncio
async def test_expectativa_gira_os_termos_e_segura_a_gramatica_nos_dois_primeiros(
    session: AsyncSession,
) -> None:
    brief = await _brief(session)
    primeiro = dialogue.expectation_for(brief, 1)
    segundo = dialogue.expectation_for(brief, 2)
    terceiro = dialogue.expectation_for(brief, 3)

    assert primeiro.target_terms == (brief.target_terms[0],)
    assert segundo.target_terms == (brief.target_terms[1],)
    # Os dois primeiros turnos existem para a conversa começar.
    assert primeiro.grammar_patterns == () and segundo.grammar_patterns == ()
    if brief.grammar_examples:
        assert terceiro.grammar_patterns == (
            brief.grammar_examples[2 % len(brief.grammar_examples)],
        )
    # Determinístico: o mesmo turno pede a mesma coisa, o que o gate humano exige.
    assert dialogue.expectation_for(brief, 1) == primeiro


@pytest.mark.asyncio
async def test_roteiro_funciona_sem_provedor_e_nao_gasta_nada(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Critério 1 do BE-46: com a assistência desligada, o Roteiro é completo."""
    monkeypatch.setattr(get_settings(), "assisted_features_enabled", False)

    def recusar(*args: object, **kwargs: object) -> None:
        raise AssertionError("o modo Roteiro não pode chamar o provedor")

    monkeypatch.setattr(assistance, "call_dialogue_provider", recusar)
    usuario = await _conta(session, "roteiro@example.com")
    lesson = await _lesson(session)
    dialogo, brief = await dialogue.create_dialogue(
        session, usuario, lesson, mode="script", operation_key=str(uuid4())
    )
    assert dialogo.mode == "script" and dialogo.provider_name is None

    resultado = await dialogue.student_turn(
        session, dialogo, brief, 1, "The train is faster than the bus.", idempotency_key="k1"
    )
    assert resultado.partner.partner_text
    assert resultado.fallback is False and resultado.error_code is None
    assert resultado.cost_microusd == 0 and resultado.checks


@pytest.mark.asyncio
async def test_modo_com_ia_e_recusado_com_a_assistencia_desligada(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "assisted_features_enabled", False)
    usuario = await _conta(session, "guiado-off@example.com")
    with pytest.raises(dialogue.DialogueUnavailable):
        await dialogue.create_dialogue(
            session, usuario, await _lesson(session), mode="guided", operation_key=str(uuid4())
        )


@pytest.mark.asyncio
async def test_criacao_e_idempotente_pela_operation_key(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "assisted_features_enabled", False)
    usuario = await _conta(session, "idem@example.com")
    lesson = await _lesson(session)
    chave = str(uuid4())
    primeiro, _ = await dialogue.create_dialogue(
        session, usuario, lesson, mode="script", operation_key=chave
    )
    segundo, _ = await dialogue.create_dialogue(
        session, usuario, lesson, mode="script", operation_key=chave
    )
    assert primeiro.id == segundo.id


def _habilitar_guiado(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_provider_kind", "gateway")
    monkeypatch.setattr(settings, "assist_dialogue_url", "https://provedor-de-teste/invalido")


@pytest.mark.asyncio
async def test_provedor_fora_do_ar_vira_roteiro_sem_perder_os_turnos_anteriores(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Critério 2 do BE-46."""
    _habilitar_guiado(monkeypatch)
    usuario = await _conta(session, "queda@example.com")
    lesson = await _lesson(session)
    dialogo, brief = await dialogue.create_dialogue(
        session, usuario, lesson, mode="guided", operation_key=str(uuid4())
    )
    # Um turno anterior já gravado: ele não pode desaparecer na queda.
    session.add(
        DialogueTurn(
            dialogue_id=dialogo.id,
            user_id=usuario.id,
            position=1,
            role="student",
            input_kind="text",
            state="completed",
            transcript="I took the train.",
            expires_at=dialogue.turn_expiry(),
        )
    )
    await session.flush()

    def cair(*args: object, **kwargs: object) -> assistance.DialogueResult:
        raise assistance.ProviderFailure("provider_unavailable")

    monkeypatch.setattr(assistance, "call_dialogue_provider", cair)
    resultado = await dialogue.student_turn(
        session, dialogo, brief, 2, "The bus is cheaper.", idempotency_key="k2"
    )
    assert resultado.fallback is True
    assert resultado.error_code == "provider_unavailable"
    assert resultado.partner.partner_text and resultado.partner.hints == ()
    # Os checks determinísticos saem igual: não dependem de rede.
    assert resultado.checks
    anteriores = (
        await session.execute(select(DialogueTurn).where(DialogueTurn.dialogue_id == dialogo.id))
    ).scalars()
    assert [turno.position for turno in anteriores] == [1]


@pytest.mark.asyncio
async def test_resposta_inventada_e_descartada_e_o_custo_continua_registrado(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Critério 4 do BE-46: código inventado, URL ou e-mail invalidam a resposta."""
    _habilitar_guiado(monkeypatch)
    usuario = await _conta(session, "inventado@example.com")
    dialogo, brief = await dialogue.create_dialogue(
        session, usuario, await _lesson(session), mode="guided", operation_key=str(uuid4())
    )

    def inventar(*args: object, **kwargs: object) -> assistance.DialogueResult:
        return assistance.DialogueResult(
            raw={
                "partner_text": "Visit https://exemplo.invalido for more.",
                "hints": [{"code": "codigo_que_nao_existe", "message": "faça assim"}],
                "confidence": 0.9,
            },
            cost_microusd=42,
            cost_known=True,
        )

    monkeypatch.setattr(assistance, "call_dialogue_provider", inventar)
    resultado = await dialogue.student_turn(session, dialogo, brief, 1, "bus", idempotency_key="k3")
    assert resultado.fallback is True
    assert resultado.error_code == "invalid_provider_response"
    # O custo aconteceu mesmo com a resposta descartada: ignorá-lo esconderia
    # consumo real da cota.
    assert resultado.cost_microusd == 42 and resultado.cost_known is True


@pytest.mark.asyncio
async def test_nenhum_texto_de_turno_entra_em_log(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Requisito do ADR, conferido no log capturado."""
    _habilitar_guiado(monkeypatch)
    segredo = "The platform at midnight was empty and cold."
    usuario = await _conta(session, "log@example.com")
    dialogo, brief = await dialogue.create_dialogue(
        session, usuario, await _lesson(session), mode="guided", operation_key=str(uuid4())
    )

    def cair(*args: object, **kwargs: object) -> assistance.DialogueResult:
        raise assistance.ProviderFailure("provider_unavailable")

    monkeypatch.setattr(assistance, "call_dialogue_provider", cair)
    with caplog.at_level(logging.DEBUG):
        resultado = await dialogue.student_turn(
            session, dialogo, brief, 1, segredo, idempotency_key="k4"
        )
    assert resultado.fallback is True
    registrado = "\n".join(record.getMessage() + str(record.__dict__) for record in caplog.records)
    assert segredo not in registrado
    assert usuario.email not in registrado
    # O que fica no log é identificador e código, o suficiente para operar.
    assert "dialogue_turn_fallback" in registrado


@pytest.mark.asyncio
async def test_dialogo_guarda_a_impressao_e_o_limite_de_turnos(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "assisted_features_enabled", False)
    usuario = await _conta(session, "limite@example.com")
    lesson = await _lesson(session)
    dialogo, brief = await dialogue.create_dialogue(
        session, usuario, lesson, mode="script", operation_key=str(uuid4())
    )
    assert dialogo.turn_limit == dialogue.MAX_TURNS_PER_DIALOGUE == 12
    assert dialogo.content_fingerprint == dialogue.content_fingerprint(brief)
    assert dialogo.rubric_version == dialogue_prompts.PROMPT_VERSION
    assert dialogo.started_at <= datetime.now(UTC)
    assert isinstance(
        (
            await session.execute(select(SpeakingDialogue).where(SpeakingDialogue.id == dialogo.id))
        ).scalar_one(),
        SpeakingDialogue,
    )
