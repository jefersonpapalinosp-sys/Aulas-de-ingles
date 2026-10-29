"""BE-46: o schema aceita o turno do Guiado e segue recusando o impossível.

As duas colunas deixaram de ser obrigatórias, e o que importa testar não é que
elas aceitam `NULL` — é que a garantia que elas carregavam **não** se perdeu:
shadowing sem cue e job de transcrição sem áudio continuam impossíveis, agora
por constraint explícita em vez de `NOT NULL`.

Os objetos são criados pelo ORM, como a aplicação faz: metade das colunas tem
default no Python e não no servidor, e um INSERT cru passaria a testar a minha
lista de colunas em vez do schema.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SpeakingAttempt, TranscriptCue, TranscriptionJob, User


async def _conta(session: AsyncSession, email: str) -> int:
    user = User(email=email, password_hash="x", display_name="BE46")
    session.add(user)
    await session.flush()
    return user.id


async def _cue(session: AsyncSession) -> int:
    return int((await session.execute(select(TranscriptCue.id).limit(1))).scalar_one())


def _tentativa(user_id: int, cue_id: int | None, origin: str) -> SpeakingAttempt:
    return SpeakingAttempt(
        user_id=user_id,
        transcript_cue_id=cue_id,
        origin=origin,
        duration_ms=1000,
        status="pending",
    )


def _job(user_id: int, attempt_id: int | None, kind: str, key: str) -> TranscriptionJob:
    agora = datetime.now(UTC)
    return TranscriptionJob(
        user_id=user_id,
        speaking_attempt_id=attempt_id,
        kind=kind,
        provider="provedor-de-teste",
        status="queued",
        idempotency_key=key,
        max_attempts=3,
        next_attempt_at=agora,
        expires_at=agora + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_audio_de_dialogo_dispensa_cue_e_shadowing_continua_exigindo(
    session: AsyncSession,
) -> None:
    user_id = await _conta(session, "be46-audio@example.com")
    cue_id = await _cue(session)

    # O caminho novo (áudio de turno de diálogo) e o antigo (shadowing)
    # convivem na mesma tabela.
    session.add_all([_tentativa(user_id, None, "dialogue"), _tentativa(user_id, cue_id, "cue")])
    await session.flush()
    total = (
        await session.execute(
            select(func.count())
            .select_from(SpeakingAttempt)
            .where(SpeakingAttempt.user_id == user_id)
        )
    ).scalar_one()
    assert total == 2

    # As duas combinações impossíveis seguem recusadas pelo banco, não só pela
    # aplicação: shadowing sem cue e diálogo com cue.
    for origin, cue in (("cue", None), ("dialogue", cue_id)):
        session.add(_tentativa(user_id, cue, origin))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


@pytest.mark.timezone
@pytest.mark.asyncio
async def test_job_de_dialogo_por_texto_dispensa_audio_e_transcricao_nao(
    session: AsyncSession,
) -> None:
    user_id = await _conta(session, "be46-job@example.com")
    cue_id = await _cue(session)
    attempt = _tentativa(user_id, cue_id, "cue")
    session.add(attempt)
    await session.flush()

    # Turno por texto: job sem áudio. Turno por voz: job com áudio.
    session.add_all(
        [
            _job(user_id, None, "dialogue", "be46-texto"),
            _job(user_id, attempt.id, "dialogue", "be46-audio"),
        ]
    )
    await session.flush()

    # Transcrição de shadowing segue precisando do áudio.
    session.add(_job(user_id, None, "transcription", "be46-sem-audio"))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
