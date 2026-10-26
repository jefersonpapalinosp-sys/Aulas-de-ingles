"""DB-46: o texto do turno vence; a evidência de que o aluno praticou fica.

É a diferença que importa deste escopo de retenção. Os outros apagam linha ou
liberam reserva; este anonimiza. Apagar o turno levaria junto `checks`, custo e
avaliação humana — o que o gate do IA-48 usa e o que o aluno vê como histórico.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import DialogueTurn, Lesson, SpeakingDialogue, User
from app.services import maintenance
from app.services.dialogue_prompts import PROMPT_VERSION


async def _turno_vencido(session: AsyncSession, *, vencido: bool) -> DialogueTurn:
    sufixo = "vencido" if vencido else "vigente"
    user = User(email=f"retencao-{sufixo}@example.com", password_hash="x", display_name="Retencao")
    session.add(user)
    await session.flush()
    lesson = (await session.execute(select(Lesson).limit(1))).scalar_one()
    agora = datetime.now(UTC)
    dialogo = SpeakingDialogue(
        user_id=user.id,
        lesson_id=lesson.id,
        operation_key=str(uuid4()),
        mode="guided",
        state="completed",
        partner_speaker="Anna",
        content_version=lesson.id,
        content_fingerprint="f" * 64,
        provider_name="provedor",
        rubric_version=PROMPT_VERSION,
        turn_limit=12,
        started_at=agora - timedelta(days=60),
    )
    session.add(dialogo)
    await session.flush()
    criado = agora - timedelta(days=60) if vencido else agora
    turno = DialogueTurn(
        dialogue_id=dialogo.id,
        user_id=user.id,
        position=1,
        role="student",
        input_kind="text",
        state="completed",
        transcript="I waited on the platform for twenty minutes.",
        checks={"target_terms_missing": True, "too_short": True},
        partner_text="That sounds like a long wait.",
        hints=[{"code": "too_short", "message": "Diga mais uma frase."}],
        confidence=0.82,
        cost_microusd=7,
        human_rating="helpful",
        created_at=criado,
        completed_at=criado,
        # `expires_at` é o que a retenção lê; o resto é só contexto realista.
        expires_at=criado + timedelta(days=30),
    )
    session.add(turno)
    await session.commit()
    return turno


@pytest.mark.asyncio
async def test_texto_vencido_sai_e_a_evidencia_permanece(session: AsyncSession) -> None:
    turno = await _turno_vencido(session, vencido=True)

    # Ensaio seco conta sem alterar nada.
    assert await maintenance.retention_batch("dialogues", apply=False, limit=10) >= 1
    await session.refresh(turno)
    assert turno.transcript is not None

    assert await maintenance.retention_batch("dialogues", apply=True, limit=10) >= 1
    await session.refresh(turno)

    # O que era do aluno sai.
    assert turno.transcript is None
    assert turno.partner_text is None
    assert turno.hints == []
    # O que prova a prática fica: a linha não é apagada.
    assert turno.state == "completed"
    assert turno.checks == {"target_terms_missing": True, "too_short": True}
    assert turno.cost_microusd == 7
    assert turno.human_rating == "helpful"
    assert turno.confidence == 0.82
    assert turno.position == 1


@pytest.mark.asyncio
async def test_turno_dentro_do_prazo_nao_e_tocado(session: AsyncSession) -> None:
    turno = await _turno_vencido(session, vencido=False)
    await maintenance.retention_batch("dialogues", apply=True, limit=10)
    await session.refresh(turno)
    assert turno.transcript is not None and turno.partner_text is not None
    assert turno.hints != []


@pytest.mark.asyncio
async def test_segunda_passada_nao_conta_o_que_ja_foi_anonimizado(
    session: AsyncSession,
) -> None:
    """Idempotência: sem isso o lote giraria para sempre sobre as mesmas linhas."""
    await _turno_vencido(session, vencido=True)
    primeira = await maintenance.retention_batch("dialogues", apply=True, limit=10)
    assert primeira >= 1
    assert await maintenance.retention_batch("dialogues", apply=False, limit=10) == 0
    assert await maintenance.retention_batch("dialogues", apply=True, limit=10) == 0


@pytest.mark.asyncio
async def test_escopo_do_dialogo_roda_sem_a_flag_de_limpeza(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O prazo de retenção é promessa, não preferência de instalação.

    Os escopos que apagam linha ou tocam arquivo ficam atrás de
    `MAINTENANCE_CLEANUP_ENABLED`; este não pode, senão uma instalação que não
    ligou a flag guardaria transcrição de aluno além do prazo. A lista de
    escopos já é afirmada em test_maintenance com o lote mockado; aqui o
    `sweep` roda o SQL de verdade, com a flag desligada, sobre um turno vencido.

    `session` não é usada só para criar o turno: é ela que arrasta
    `banco_por_teste`, que descarta o engine no teardown. Sem isso o pool fica
    com conexões presas no event loop deste teste e o teste seguinte que abrir
    conexão falha com "attached to a different loop".
    """
    turno = await _turno_vencido(session, vencido=True)
    monkeypatch.setattr(get_settings(), "maintenance_cleanup_enabled", False)

    counts = await maintenance.sweep()

    assert counts["dialogues"] >= 1
    assert "pending" not in counts
    await session.refresh(turno)
    assert turno.transcript is None


@pytest.mark.asyncio
async def test_escopo_invalido_e_recusado_antes_do_banco() -> None:
    with pytest.raises(ValueError):
        await maintenance.retention_batch("dialogues; DROP TABLE dialogue_turn", apply=True)
