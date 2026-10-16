"""Exclusão da conta no banco e limpeza retomável dos arquivos de voz."""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import conferir_senha
from app.db.models import AccountDeletionFile, AccountDeletionJob, SpeakingAttempt, User
from app.db.session import get_sessionmaker
from app.schemas.notebook import AccountDeletionIn, AccountDeletionOut
from app.services.audio_storage import AudioStorage
from app.services.auth_limits import password_work

MAX_FILE_ATTEMPTS = 10


async def delete_account(
    session: AsyncSession,
    user_id: int,
    password_hash: str,
    request: AccountDeletionIn,
) -> AccountDeletionOut:
    """Apaga dados relacionais e deixa somente tarefas opacas de arquivo."""

    # Argon2 não segura conexão nem lock. A senha pode ter sido trocada nesse
    # intervalo; o hash é comparado novamente dentro da transação destrutiva.
    await session.rollback()
    valid = await password_work(
        conferir_senha,
        request.password.get_secret_value(),
        password_hash,
    )
    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Senha incorreta.")

    operation_key = str(request.operation_key)
    async with session.begin():
        await session.execute(select(func.pg_advisory_xact_lock(4040, user_id)))
        user = (
            await session.execute(select(User).where(User.id == user_id).with_for_update())
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Conta inexistente.",
            )
        if user.password_hash != password_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A senha mudou durante a confirmação. Entre novamente.",
            )
        if await session.get(AccountDeletionJob, operation_key) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Identificador de exclusão já utilizado.",
            )

        storage_keys = list(
            dict.fromkeys(
                (
                    await session.execute(
                        select(SpeakingAttempt.storage_key)
                        .where(
                            SpeakingAttempt.user_id == user_id,
                            SpeakingAttempt.storage_key.is_not(None),
                        )
                        .order_by(SpeakingAttempt.id)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
        )
        state = "cleanup_pending" if storage_keys else "completed"
        job = AccountDeletionJob(
            operation_key=operation_key,
            state=state,
            file_count=len(storage_keys),
            deleted_file_count=0,
            completed_at=None if storage_keys else datetime.now(UTC),
        )
        session.add(job)
        # Não há relacionamento ORM intencional entre recibo e tarefas; force a
        # ordem do FK antes de enfileirar as chaves opacas.
        await session.flush()
        session.add_all(
            AccountDeletionFile(job_operation_key=operation_key, storage_key=key)
            for key in storage_keys
            if key is not None
        )
        await session.delete(user)
        await session.flush()

    return AccountDeletionOut(
        operation_key=operation_key,
        state=state,  # type: ignore[arg-type]
        audio_files_pending=len(storage_keys),
    )


async def process_file_batch(*, limit: int | None = None) -> int:
    """Remove arquivos um a um; unlink repetido continua sendo sucesso."""

    settings = get_settings()
    batch = min(limit or settings.maintenance_batch_size, settings.maintenance_batch_size)
    processed = 0
    for _ in range(batch):
        async with get_sessionmaker()() as session, session.begin():
            now = datetime.now(UTC)
            task = (
                await session.execute(
                    select(AccountDeletionFile)
                    .join(
                        AccountDeletionJob,
                        AccountDeletionJob.operation_key == AccountDeletionFile.job_operation_key,
                    )
                    .where(
                        AccountDeletionFile.next_attempt_at <= now,
                        AccountDeletionJob.state == "cleanup_pending",
                    )
                    .order_by(AccountDeletionFile.next_attempt_at, AccountDeletionFile.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if task is None:
                break
            job = (
                await session.execute(
                    select(AccountDeletionJob)
                    .where(AccountDeletionJob.operation_key == task.job_operation_key)
                    .with_for_update()
                )
            ).scalar_one()
            task.attempt_count += 1
            try:
                await asyncio.to_thread(
                    AudioStorage(settings.speaking_storage_dir).delete,
                    task.storage_key,
                )
            except (OSError, ValueError):
                task.last_error_code = "audio_delete_failed"
                job.last_error_code = "audio_delete_failed"
                if task.attempt_count >= MAX_FILE_ATTEMPTS:
                    job.state = "failed"
                else:
                    delay = min(3600, 2 ** min(task.attempt_count, 10))
                    task.next_attempt_at = now + timedelta(seconds=delay)
            else:
                job.deleted_file_count += 1
                job.last_error_code = None
                await session.delete(task)
                if job.deleted_file_count == job.file_count:
                    job.state = "completed"
                    job.completed_at = now
            processed += 1
    return processed


async def status_counts() -> dict[str, int]:
    """Métricas agregadas para o heartbeat; nunca expõe chave ou identidade."""

    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(AccountDeletionJob.state, func.count())
                .where(AccountDeletionJob.state.in_(("cleanup_pending", "failed")))
                .group_by(AccountDeletionJob.state)
            )
        ).all()
    counts = {state: int(count) for state, count in rows}
    return {
        "account_deletions_pending": counts.get("cleanup_pending", 0),
        "account_deletions_failed": counts.get("failed", 0),
    }
