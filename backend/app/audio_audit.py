"""python -m app.audio_audit --dry-run. Não existe modo apply/delete."""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.models import SpeakingAttempt
from app.db.session import dispose_engine, get_sessionmaker
from app.services.audio_audit import MAX_ROWS, AudioReference, inventory


async def audit() -> dict[str, Any]:
    try:
        async with get_sessionmaker()() as session:
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            now = await session.scalar(select(func.now()))
            assert isinstance(now, datetime)
            rows = (
                await session.execute(
                    select(
                        SpeakingAttempt.id,
                        SpeakingAttempt.status,
                        SpeakingAttempt.storage_key,
                        SpeakingAttempt.file_size,
                        SpeakingAttempt.created_at,
                        SpeakingAttempt.audio_sha256,
                    )
                    .order_by(SpeakingAttempt.id)
                    .limit(MAX_ROWS + 1)
                )
            ).all()
            references = [AudioReference(*row) for row in rows[:MAX_ROWS]]
            await session.rollback()
        # Nenhuma transação aberta durante a leitura/hash dos arquivos.
        return await asyncio.to_thread(
            inventory,
            Path(get_settings().speaking_storage_dir),
            references,
            now,
            snapshot_complete=len(rows) <= MAX_ROWS,
        )
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", required=True)
    parser.parse_args()
    try:
        report = asyncio.run(audit())
    except Exception:
        # Nunca imprimir DATABASE_URL, credenciais ou conteúdo dos arquivos.
        print(json.dumps({"dry_run": True, "complete": False, "error": "audit_unavailable"}))
        raise SystemExit(2) from None
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if not report["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
