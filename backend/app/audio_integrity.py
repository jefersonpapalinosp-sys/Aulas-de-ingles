"""Confere uma referência de áudio; dry-run padrão, sem exclusão de arquivos.

--apply grava estado observado. --baseline estabelece hash do arquivo atualmente
presente, nunca prova histórica retroativa. --restore-file exige SHA de backup
conferido e ausência do arquivo original; publica nova chave sem sobrescrever bytes.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.models import SpeakingAttempt
from app.db.session import dispose_engine, get_sessionmaker
from app.domain.enums import IntegrityState
from app.services.audio_inspection import inspect_audio
from app.services.audio_storage import AudioStorage


async def execute(
    *,
    attempt_id: int,
    apply: bool = False,
    baseline: bool = False,
    confirm_database: str | None = None,
    confirm_storage: str | None = None,
    expected_key: str | None = None,
    restore_file: str | None = None,
    sha256: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    root = Path(settings.speaking_storage_dir)
    if (
        not root.is_absolute()
        or root.resolve(strict=True) != root
        or len(root.parts) < 3
        or root == Path.home()
    ):
        raise ValueError("unsafe_storage")
    if (baseline or restore_file) and not apply:
        raise ValueError("apply_required")
    if apply and (confirm_storage != str(root) or not confirm_database or not expected_key):
        raise ValueError("target_confirmation_required")
    if settings.app_env == "prod" and apply and settings.database_purpose != "migrator":
        raise ValueError("operator_role_required")
    storage = AudioStorage(str(root))
    async with get_sessionmaker()() as session:
        await session.execute(text("SET LOCAL lock_timeout = '1s'"))
        await session.execute(text("SET LOCAL statement_timeout = '5s'"))
        database = await session.scalar(select(func.current_database()))
        if apply and database != confirm_database:
            raise ValueError("database_confirmation_mismatch")
        query = select(SpeakingAttempt).where(SpeakingAttempt.id == attempt_id)
        if apply:
            query = query.with_for_update(of=SpeakingAttempt, nowait=True)
        attempt = await session.scalar(query)
        if attempt is None or attempt.status != "ready" or not attempt.storage_key:
            raise ValueError("ready_attempt_required")
        if apply and expected_key != attempt.storage_key:
            raise ValueError("reference_changed")
        old_key = attempt.storage_key
        baseline_established = False
        if restore_file:
            if not sha256 or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
                raise ValueError("backup_checksum_required")
            if attempt.audio_sha256 and attempt.audio_sha256 != sha256:
                raise ValueError("backup_does_not_match_baseline")
            if os.path.lexists(root / old_key):
                raise ValueError("existing_file_protected")
            source = Path(restore_file)
            if not source.is_absolute() or source.parent.resolve(strict=True) != source.parent:
                raise ValueError("unsafe_backup_path")
            data = AudioStorage(str(source.parent)).read_verified(
                source.name, sha256, settings.speaking_max_bytes
            )
            if len(data) != attempt.file_size or not attempt.mime_type:
                raise ValueError("backup_metadata_mismatch")
            duration = await inspect_audio(data, attempt.mime_type)
            if abs(duration - attempt.duration_ms) > 250:
                raise ValueError("backup_duration_mismatch")
            # Commit incerto preserva candidato para auditoria/quarentena;
            # nunca excluir um arquivo potencialmente referenciado.
            attempt.storage_key = storage.save(data, attempt.mime_type)
            attempt.audio_sha256 = sha256
            observed: IntegrityState = "verified"
        else:
            try:
                data = storage.read_verified(
                    old_key, attempt.audio_sha256, settings.speaking_max_bytes
                )
            except FileNotFoundError:
                observed = "missing"
            except (OSError, ValueError):
                observed = "changed"
            else:
                observed = "verified" if attempt.audio_sha256 else "unknown"
                if len(data) != attempt.file_size:
                    observed = "changed"
                elif baseline and not attempt.audio_sha256:
                    attempt.audio_sha256 = hashlib.sha256(data).hexdigest()
                    baseline_established = True
                    observed = "verified"
        result = {
            "attempt_id": attempt_id,
            "dry_run": not apply,
            "state": observed,
            "baseline_established": baseline_established,
            "restored": bool(restore_file),
        }
        if apply:
            attempt.integrity_state = observed
            attempt.integrity_checked_at = datetime.now(UTC)
            await session.commit()
        else:
            await session.rollback()
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--confirm-database")
    parser.add_argument("--confirm-storage")
    parser.add_argument("--expected-key")
    parser.add_argument("--restore-file")
    parser.add_argument("--sha256")
    args = parser.parse_args()

    async def run() -> dict[str, Any]:
        try:
            return await execute(**vars(args))
        finally:
            await dispose_engine()

    try:
        print(json.dumps(asyncio.run(run()), sort_keys=True))
    except Exception:
        print(json.dumps({"complete": False, "error": "integrity_operation_refused"}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
