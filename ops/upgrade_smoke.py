"""Backup, restore e upgrade real exclusivamente no laboratório DB-42."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

from app.api.health import required_schema_heads

from ops.recovery import (
    BACKUPS,
    CONFIRM_UPGRADE42,
    HELPER,
    ROOT,
    SNAPSHOT_SQL,
    UPGRADE_FROM,
    UPGRADE_LAB,
    UPGRADE_PROJECT,
    UPGRADE_RESTORE,
    backup,
    check_target,
    docker,
    query,
    quiet,
    restore,
    voice,
)
from ops.recovery_archive import (
    audio_inventory,
    file_info,
    require,
    verify_bundle,
    write_json,
)
from ops.rollback_image import IMAGE as ROLLBACK_IMAGE
from ops.rollback_image import REVISION as ROLLBACK_REVISION

PERSONAL_COUNTS = {
    "users": 1,
    "speaking": 1,
    "writing_feedback": 1,
    "writing_drafts": 1,
    "writing_revisions": 1,
    "attempts": 1,
    "practice_sessions": 1,
    "practice_items": 1,
    "review_items": 1,
    "study_sessions": 1,
    "step_progress": 2,
    "activity_sessions": 1,
    "activity_events": 1,
    "active_intervals": 1,
    "media_progress": 1,
    "lesson_progress": 1,
    "notebook_entries": 1,
    "transcription_jobs": 1,
}


def app_args(*command: str, voice_read_only: bool = False) -> list[str]:
    args = [
        "run",
        "--rm",
        "--network",
        f"{UPGRADE_PROJECT}_default",
        "-e",
        "APP_ENV=dev",
        "-e",
        "DATABASE_URL=postgresql+asyncpg://aulas_restore:restore_disposable_only@target-db:5432/aulas_ingles_restore",
        "-e",
        "SPEAKING_STORAGE_DIR=/app/data/speaking",
    ]
    if voice_read_only:
        args += [
            "--user",
            "10001:10001",
            "--entrypoint",
            "python",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=volume,src={UPGRADE_RESTORE.voice_volume},dst=/app/data/speaking,readonly",
            "--mount",
            f"type=bind,src={ROOT / 'ops'},dst=/tools,readonly",
            HELPER,
        ]
    else:
        args.append(HELPER)
    return [*args, *command]


def migrate_with_lock_sampling() -> tuple[float, int]:
    name = "aulas-upgrade42-migration"
    started = time.monotonic()
    container_id = (
        docker(
            "run",
            "-d",
            "--name",
            name,
            "--network",
            f"{UPGRADE_PROJECT}_default",
            "-e",
            "APP_ENV=dev",
            "-e",
            "DATABASE_URL=postgresql+asyncpg://aulas_restore:restore_disposable_only@target-db:5432/aulas_ingles_restore",
            HELPER,
            "alembic",
            "upgrade",
            "head",
        )
        .decode()
        .strip()
    )
    maximum_waiting = 0
    try:
        while True:
            running = (
                docker("inspect", "--format", "{{.State.Running}}", container_id)
                .decode()
                .strip()
            )
            locks = query(
                UPGRADE_RESTORE,
                "SELECT json_build_object('waiting',count(*)) FROM pg_locks WHERE NOT granted",
            )
            maximum_waiting = max(maximum_waiting, int(locks["waiting"]))
            if running != "true":
                break
            require(time.monotonic() - started < 180, "Migration excedeu 180 segundos.")
            time.sleep(0.02)
        exit_code = docker("wait", container_id).decode().strip()
        require(exit_code == "0", "Migration falhou; destino parcial foi preservado.")
    finally:
        docker("rm", container_id)
    return round(time.monotonic() - started, 3), maximum_waiting


def rollback_application_probe() -> dict[str, object]:
    name = "aulas-upgrade42-rollback-api"
    container_id = (
        docker(
            "run",
            "-d",
            "--name",
            name,
            "--network",
            f"{UPGRADE_PROJECT}_default",
            "--network-alias",
            "rollback-api",
            "-e",
            "APP_ENV=dev",
            "-e",
            "DATABASE_URL=postgresql+asyncpg://aulas_restore:restore_disposable_only@target-db:5432/aulas_ingles_restore",
            ROLLBACK_IMAGE,
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--workers",
            "1",
        )
        .decode()
        .strip()
    )
    try:
        probe = json.loads(
            docker(
                "run",
                "--rm",
                "--network",
                f"{UPGRADE_PROJECT}_default",
                "--entrypoint",
                "python",
                "--mount",
                f"type=bind,src={ROOT / 'ops'},dst=/tools,readonly",
                HELPER,
                "/tools/rollback_http_probe.py",
                timeout=90,
            )
        )
        require(
            probe.get("verified") is True, "Imagem anterior não leu o schema expandido."
        )
        image_id = json.loads(docker("image", "inspect", ROLLBACK_IMAGE))[0]["Id"]
        return {
            "verified": True,
            "revision": ROLLBACK_REVISION,
            "image_id": image_id,
            "health": probe["health"],
            "catalog_nonempty": probe["catalog_nonempty"],
        }
    finally:
        docker("rm", "-f", container_id)


def post_restore_invariants() -> dict[str, object]:
    """Prova identidade limitada e garantias referenciais no clone restaurado."""
    role = query(
        UPGRADE_RESTORE,
        """
        SELECT json_build_object(
          'role', current_user,
          'database_owner', pg_get_userbyid(d.datdba),
          'can_connect', has_database_privilege(current_user,current_database(),'CONNECT'),
          'superuser', r.rolsuper,
          'createdb', r.rolcreatedb,
          'createrole', r.rolcreaterole,
          'bypassrls', r.rolbypassrls,
          'replication', r.rolreplication)
        FROM pg_database d JOIN pg_roles r ON r.rolname=current_user
        WHERE d.datname=current_database()
        """,
    )
    require(
        role["role"] == "aulas_restore"
        and role["database_owner"] == "aulas_restore"
        and role["can_connect"] is True
        and not any(
            role[key]
            for key in (
                "superuser",
                "createdb",
                "createrole",
                "bypassrls",
                "replication",
            )
        ),
        "Papel pós-restore não está limitado ao destino esperado.",
    )
    references = query(
        UPGRADE_RESTORE,
        """
        SELECT json_build_object(
          'foreign_keys', count(*),
          'unvalidated', count(*) FILTER (WHERE NOT convalidated))
        FROM pg_constraint
        WHERE contype='f' AND connamespace='public'::regnamespace
        """,
    )
    require(
        int(references["foreign_keys"]) > 0 and int(references["unvalidated"]) == 0,
        "Integridade referencial pós-restore não está integralmente validada.",
    )
    return {"role": role, "referential_constraints": references}


def main() -> None:
    recovery_started = time.monotonic()
    os.umask(0o077)
    check_target(UPGRADE_LAB)
    check_target(UPGRADE_RESTORE)
    source = query(UPGRADE_LAB, SNAPSHOT_SQL)
    require(
        source["revision"] == [UPGRADE_FROM], "Origem não está na revisão anterior."
    )
    require(
        all(
            source["counts"].get(name) == expected
            for name, expected in PERSONAL_COUNTS.items()
        ),
        "Fixture multimodal sintética incompleta.",
    )
    bundle = backup("upgrade-lab")
    manifest = verify_bundle(bundle)
    require(manifest["snapshot"] == source, "Backup não representa a origem sintética.")
    restore_receipt = restore(bundle, CONFIRM_UPGRADE42)
    before = query(UPGRADE_RESTORE, SNAPSHOT_SQL)
    with tempfile.TemporaryDirectory(prefix="aulas-upgrade42-before-") as temporary:
        before_voice = Path(temporary) / "voice.tar"
        with before_voice.open("xb") as stream:
            voice(UPGRADE_RESTORE, "export", stdout=stream)
        before_inventory = audio_inventory(before_voice)

    quiet(UPGRADE_RESTORE)
    waiting_before = int(
        query(
            UPGRADE_RESTORE,
            "SELECT json_build_object('waiting',count(*)) FROM pg_locks WHERE NOT granted",
        )["waiting"]
    )
    migration_seconds, maximum_waiting = migrate_with_lock_sampling()
    docker(*app_args("alembic", "check"), timeout=120)
    application = json.loads(
        docker(
            *app_args("/tools/upgrade_application_check.py", voice_read_only=True),
            timeout=120,
        )
    )
    require(application["verified"] is True, "Aplicação não leu o clone restaurado.")
    post_restore = post_restore_invariants()
    rollback_application = rollback_application_probe()
    after = query(UPGRADE_RESTORE, SNAPSHOT_SQL)
    with tempfile.TemporaryDirectory(prefix="aulas-upgrade42-after-") as temporary:
        after_voice = Path(temporary) / "voice.tar"
        with after_voice.open("xb") as stream:
            voice(UPGRADE_RESTORE, "export", stdout=stream)
        after_inventory = audio_inventory(after_voice)
    waiting_after = int(
        query(
            UPGRADE_RESTORE,
            "SELECT json_build_object('waiting',count(*)) FROM pg_locks WHERE NOT granted",
        )["waiting"]
    )
    require(
        after["revision"] == list(required_schema_heads()),
        "Upgrade não chegou ao head.",
    )
    require(after["counts"] == before["counts"], "Contagens mudaram durante o upgrade.")
    require(after["audio"] == before["audio"], "Referências de voz mudaram no upgrade.")
    require(after_inventory == before_inventory, "Checksums de voz mudaram no upgrade.")
    require(waiting_after == 0, "Upgrade deixou lock aguardando.")
    quiet(UPGRADE_RESTORE)
    technical_recovery_seconds = round(time.monotonic() - recovery_started, 3)

    receipts = BACKUPS / "upgrade-receipts"
    require(
        not BACKUPS.is_symlink() and not receipts.is_symlink(),
        "Destino de recibo inseguro.",
    )
    receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(receipts.stat().st_mode & 0o077 == 0, "Recibos devem ser privados.")
    receipt = receipts / f"{manifest['bundle_id']}.json"
    write_json(
        receipt,
        {
            "verified": True,
            "bundle_id": manifest["bundle_id"],
            "manifest": file_info(Path(bundle) / "manifest.json"),
            "restore_receipt": file_info(restore_receipt),
            "from_revision": before["revision"],
            "to_revision": after["revision"],
            "counts": after["counts"],
            "audio_files": len(after_inventory),
            "application_read": application,
            "application_rollback": rollback_application,
            "post_restore_invariants": post_restore,
            "migration_seconds": migration_seconds,
            "technical_recovery_seconds": technical_recovery_seconds,
            "rto_target_seconds": 3600,
            "within_technical_rto_target": technical_recovery_seconds <= 3600,
            "rpo_cadence_verified": False,
            "waiting_locks_before": waiting_before,
            "maximum_waiting_locks_sampled": maximum_waiting,
            "waiting_locks_after": waiting_after,
        },
    )
    print(
        json.dumps(
            {
                "verified": True,
                "receipt": str(receipt),
                "migration_seconds": migration_seconds,
                "technical_recovery_seconds": technical_recovery_seconds,
                "maximum_waiting_locks_sampled": maximum_waiting,
                "modalities": sorted(PERSONAL_COUNTS),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--rollback-only"]:
            check_target(UPGRADE_RESTORE)
            require(
                query(UPGRADE_RESTORE, SNAPSHOT_SQL)["revision"]
                == list(required_schema_heads()),
                "Clone não está no schema expandido atual.",
            )
            print(json.dumps(rollback_application_probe(), indent=2))
        elif sys.argv[1:] == ["--post-restore-only"]:
            check_target(UPGRADE_RESTORE)
            print(json.dumps(post_restore_invariants(), indent=2))
        elif sys.argv[1:]:
            raise ValueError("Argumento inválido.")
        else:
            main()
    except Exception:
        print(
            "Ensaio de upgrade falhou; preserve volumes/pacote/recibos.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
