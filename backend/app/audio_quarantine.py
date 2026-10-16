"""Operador dev/test: quarentena reversível explícita; nunca expurga nem repara SQL.

Comece por python -m app.audio_audit --dry-run. Uma operação por chamada, com UUID
fornecido antes da ação, checksum e confirmação explícita do banco e diretório.
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.models import SpeakingAttempt
from app.db.session import dispose_engine, get_sessionmaker
from app.services.audio_quarantine import Quarantine, QuarantineRefused


async def execute(
    *,
    action: str,
    operation: str,
    confirm_storage: str,
    confirm_database: str,
    key: str | None = None,
    digest: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if settings.app_env == "prod" and settings.database_purpose != "migrator":
        raise QuarantineRefused("production_operator_role_required")
    if confirm_storage != settings.speaking_storage_dir or not confirm_database:
        raise QuarantineRefused("target_confirmation_required")
    if action not in {"quarantine", "resume", "restore"}:
        raise QuarantineRefused("invalid_action")
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            database = await session.scalar(select(func.current_database()))
            if database != confirm_database:
                raise QuarantineRefused("database_confirmation_mismatch")
            # NOWAIT: não formar fila nem intervir em upload/delete já em andamento.
            # EXCLUSIVE também conflita com FOR UPDATE usado pela API antes do save.
            await session.execute(text("LOCK TABLE speaking_attempt IN EXCLUSIVE MODE NOWAIT"))
            now = await session.scalar(select(func.clock_timestamp()))
            with Quarantine(Path(confirm_storage), str(database)) as storage:
                if action == "quarantine":
                    if key is None or digest is None:
                        raise QuarantineRefused("key_and_checksum_required")
                    selected_key = key
                    record = None
                else:
                    record = storage.load(operation)
                    selected_key = record["key"]
                referenced = await session.scalar(
                    select(SpeakingAttempt.id)
                    .where(SpeakingAttempt.storage_key == selected_key)
                    .limit(1)
                )
                # Restaurar devolve bytes; não cria referência nem publica tentativa pending.
                # Resume permanece conservador: referência nova exige --restore explícito.
                if referenced is not None and action != "restore":
                    raise QuarantineRefused("referenced_file_protected")
                if record is None:
                    assert key is not None and digest is not None and now is not None
                    record = storage.prepare(key, digest, operation, now)
                # IO síncrono e limitado em processo CLI dedicado: cancelamento não deixa
                # uma thread movendo arquivos depois da liberação do lock SQL.
                result = storage.finish(record, restore=action == "restore")
            await session.rollback()
            return result
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("quarantine", "resume", "restore"))
    parser.add_argument("--operation", required=True)
    parser.add_argument("--confirm-storage", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--key")
    parser.add_argument("--sha256", dest="digest")
    args = parser.parse_args()
    if args.action == "quarantine" and (not args.key or not args.digest):
        parser.error("quarantine exige --key e --sha256")
    if args.action != "quarantine" and (args.key or args.digest):
        parser.error("resume/restore usam somente o alvo do journal")
    try:
        report = asyncio.run(execute(**vars(args)))
    except Exception as error:
        code = str(error) if isinstance(error, QuarantineRefused) else "operation_unavailable"
        print(json.dumps({"complete": False, "operation": args.operation, "error": code}))
        raise SystemExit(2) from None
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
