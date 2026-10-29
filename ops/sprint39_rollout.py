"""39G/H: captura, ensaio HTTP e aplicação, sem seed nem restauração na origem.

Exige origem em manutenção, backup conferido e clone exclusivo vazio restaurado.
Recibos vinculam imagem imutável, script, backup e fingerprints históricos.
Falha mantém manutenção; nunca faz downgrade ou reabre serviços automaticamente.
"""

import argparse
import json
import os
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from ops import (
    assist_alignment,
    concurrency_rollout,
    dev_alignment,
    recovery,
    roles,
    study_rollout,
)
from ops.recovery_archive import RecoveryError, file_info, require, verify_bundle, write_json

HEAD = "a39d7bc02486"
BASES = {"dev": "f28c6abe1375", "prod": "d06a4e9cb153"}
CLONES = {"dev": recovery.DEV39_CHECK, "prod": recovery.STUDY39_CHECK}
SMOKE = recovery.ROOT / "ops/assist_alignment_smoke.py"
INTEGRITY_COLUMNS = ["audio_sha256", "integrity_state", "integrity_checked_at"]


def fingerprints(
    target: recovery.Target, scope: str
) -> dict[str, study_rollout.Fingerprint]:
    require(scope in BASES, "Origem inválida.")
    columns = {"speaking_attempt": INTEGRITY_COLUMNS}
    tables = ["worker_heartbeat"]
    if scope == "prod":
        columns.update(
            {
                "media_progress": [
                    "revision",
                    "completed",
                    "operation_key",
                    "fingerprint",
                    "changed_at",
                ],
                "study_plan": ["timezone"],
                "writing_feedback": ["assist_reservation_id"],
                "transcription_job": ["assist_reservation_id"],
            }
        )
        tables += [
            "assist_reservation",
            "study_activity_session",
            "study_activity_event",
            "study_active_interval",
        ]
    return study_rollout.fingerprints(target, excluded_columns=columns, excluded_tables=tables)


def configuration(target: recovery.Target, scope: str, clone: bool = False) -> str:
    require(scope in BASES, "Origem inválida.")
    if clone:
        require(target == CLONES[scope], "Clone inesperado.")
        return (
            "APP_ENV=dev\nASSISTED_FEATURES_ENABLED=false\nLOG_LEVEL=warning\n"
            "DATABASE_URL=postgresql+asyncpg://aulas_restore:restore_disposable_only"
            f"@{target.service}:5432/aulas_ingles_restore\n"
        )
    require(target == recovery.source_target(scope), "Origem não confirmada.")
    env = recovery.env_of(recovery.container(target.project, "api"))
    if scope == "prod":
        require(
            env.get("DATABASE_PURPOSE") == "runtime",
            "Estudo deve usar runtime limitado.",
        )
        require((roles.SECRETS / "roles-prod.json").is_file(), "Credenciais ausentes.")
        password = roles.private_credentials("prod")["aulas_migrator"]
        url = (
            f"postgresql+asyncpg://aulas_migrator:{quote(password, safe='')}"
            f"@db:5432/{target.database}"
        )
        secret = env.get("JWT_SECRET", "")
        require(
            len(secret) >= 32 and "\n" not in secret and "\r" not in secret,
            "Segredo inválido.",
        )
        return (
            f"APP_ENV=prod\nDATABASE_PURPOSE=migrator\nJWT_SECRET={secret}\n"
            f"DATABASE_URL={url}\nASSISTED_FEATURES_ENABLED=false\n"
        )
    url = env.get("DATABASE_URL", "")
    parsed = urlsplit(url)
    require(
        parsed.scheme == "postgresql+asyncpg"
        and parsed.hostname == "db"
        and parsed.port in (None, 5432)
        and parsed.path == f"/{target.database}"
        and unquote(parsed.username or "") == target.role
        and not parsed.query
        and not parsed.fragment
        and "\n" not in url
        and "\r" not in url,
        "Conexão DEV divergente.",
    )
    return f"APP_ENV=dev\nDATABASE_URL={url}\nASSISTED_FEATURES_ENABLED=false\n"


def migrate(target: recovery.Target, scope: str, image: str, clone: bool) -> None:
    with tempfile.NamedTemporaryFile(mode="w", prefix="aulas-39-migrate-") as env:
        env.write(configuration(target, scope, clone))
        env.flush()
        for command in (("upgrade", HEAD), ("upgrade", HEAD), ("check",)):
            recovery.docker(
                "run",
                "--rm",
                "--read-only",
                "--user",
                "10001:10001",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--network",
                f"{target.project}_default",
                "--env-file",
                env.name,
                "--entrypoint",
                "alembic",
                image,
                *command,
                timeout=300,
            )


def smoke_clone(target: recovery.Target, scope: str, image: str) -> dict[str, object]:
    with tempfile.NamedTemporaryFile(mode="w", prefix="aulas-39-smoke-") as env:
        env.write(configuration(target, scope, True))
        env.flush()
        cid = (
            recovery.docker(
                "run",
                "-d",
                "--read-only",
                "--user",
                "10001:10001",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--network",
                f"{target.project}_default",
                "--env-file",
                env.name,
                "--entrypoint",
                "uvicorn",
                image,
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--no-access-log",
            )
            .decode()
            .strip()
        )
    try:
        for attempt in range(20):
            try:
                recovery.docker(
                    "exec",
                    cid,
                    "python",
                    "-c",
                    "import urllib.request; "
                    "urllib.request.urlopen('http://127.0.0.1:8000/api/live', timeout=2)",
                    timeout=5,
                )
                break
            except RecoveryError:
                if attempt == 19:
                    raise
                time.sleep(1)
        with SMOKE.open("rb") as stream:
            result = json.loads(
                recovery.docker("exec", "-i", cid, "python", "-", stdin=stream, timeout=90)
            )
        return assist_alignment.checked_smoke(result)
    finally:
        recovery.docker("stop", cid, timeout=30)
        recovery.docker("rm", cid)


def validate_receipt(
    receipt: Mapping[str, object], binding: Mapping[str, object], clone: recovery.Target
) -> None:
    require(
        all(receipt.get(k) == v for k, v in binding.items())
        and receipt.get("verified") is True
        and receipt.get("revision") == HEAD
        and receipt.get("target") == f"{clone.project}/{clone.service}",
        "Ensaio obrigatório da mesma imagem/script/backup não comprovado.",
    )
    assist_alignment.checked_smoke(receipt.get("http"))


def run(action: str, backup: Path, scope: str) -> None:
    require(
        action in {"capture", "rehearse", "apply"} and scope in BASES,
        "Ação/alvo inválidos.",
    )
    manifest = verify_bundle(backup)
    origin = study_rollout.json_object(manifest.get("source"))
    snapshot = study_rollout.json_object(manifest.get("snapshot"))
    audio_files = study_rollout.json_object(manifest.get("audio_files"))
    source, clone = recovery.source_target(scope), CLONES[scope]
    info = recovery.check_target(source)
    recovery.quiet(source)
    require(
        origin.get("kind") == scope
        and origin.get("project") == source.project
        and origin.get("database") == source.database
        and origin.get("db_container_id") == info["Id"]
        and origin.get("voice_volume") == source.voice_volume
        and snapshot.get("revision") == [BASES[scope]],
        "Backup/origem divergentes.",
    )
    image = dev_alignment.image_id()
    binding: dict[str, object] = {
        "manifest": file_info(backup / "manifest.json"),
        "tools_image": image,
        "smoke_script": file_info(SMOKE),
        "rollout_script": file_info(Path(__file__)),
    }
    prefix = recovery.BACKUPS / f"sprint39-{scope}-{manifest['bundle_id']}"
    capture = Path(f"{prefix}-capture.json")
    rehearsal = Path(f"{prefix}-rehearse.json")
    with recovery.lease("sprint39-rollout"):
        require(
            recovery.query(source, recovery.SNAPSHOT_SQL) == manifest["snapshot"],
            "Origem mudou após backup.",
        )
        dev_alignment.verify_voice(source, manifest)
        if action == "capture":
            require(
                not capture.exists(),
                "Captura existente protegida; não sobrescrever prova.",
            )
            write_json(
                capture,
                {
                    **binding,
                    "tables": fingerprints(source, scope),
                    "audit": concurrency_rollout.audit(source, preserve_legacy=True),
                },
            )
            print("Captura privada concluída; nenhum dado pessoal exposto.")
            return
        proof = concurrency_rollout.private_json(capture)
        tables = study_rollout.checked_fingerprints(proof.get("tables"))
        expected_audit = concurrency_rollout.checked_audit(proof.get("audit"))
        require(
            all(proof.get(k) == v for k, v in binding.items()),
            "Imagem/script/backup mudou.",
        )
        require(fingerprints(source, scope) == tables, "Histórico de origem mudou.")
        if action == "rehearse":
            restored = concurrency_rollout.private_json(
                recovery.BACKUPS / "restore-receipts" / f"{manifest['bundle_id']}.json"
            )
            require(
                restored.get("verified") is True
                and restored.get("manifest") == binding["manifest"]
                and restored.get("target") == f"{clone.project}/{clone.service}",
                "Restore exclusivo não comprovado.",
            )
            target = clone
        else:
            validate_receipt(concurrency_rollout.private_json(rehearsal), binding, clone)
            target = source
        recovery.check_target(target)
        recovery.quiet(target)
        require(
            recovery.query(target, recovery.SNAPSHOT_SQL) == manifest["snapshot"]
            and fingerprints(target, scope) == tables,
            "Destino divergente.",
        )
        dev_alignment.verify_voice(target, manifest)
        started = time.monotonic()
        migrate(target, scope, image, action == "rehearse")
        elapsed = round(time.monotonic() - started, 2)
        if scope == "prod":
            assist_alignment.verify_backfill(target)
        require(
            study_rollout.query_count(
                target,
                "SELECT count(*) FROM speaking_attempt WHERE audio_sha256 IS NOT NULL "
                "OR integrity_state != 'unknown' OR integrity_checked_at IS NOT NULL",
            )
            == 0,
            "Baseline histórico inventado.",
        )
        http = smoke_clone(target, scope, image) if action == "rehearse" else None
        recovery.quiet(target)
        require(
            recovery.query(target, recovery.SNAPSHOT_SQL)
            == {**snapshot, "revision": [HEAD]}
            and fingerprints(target, scope) == tables,
            "Dados históricos divergiram; não reabrir.",
        )
        concurrency_rollout.audit(target, preserve_legacy=True, expected=expected_audit)
        dev_alignment.verify_voice(target, manifest)
        result = {
            **binding,
            "verified": True,
            "revision": HEAD,
            "target": f"{target.project}/{target.service}",
            "http": http,
            "migration_seconds": elapsed,
            "tables": len(tables),
            "rows": sum(t["count"] for t in tables.values()),
            "audio_count": len(audio_files),
        }
        write_json(Path(f"{prefix}-{action}.json"), result)
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in (
                        "verified",
                        "revision",
                        "target",
                        "migration_seconds",
                        "tables",
                        "rows",
                        "audio_count",
                    )
                }
            )
        )


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "rehearse", "apply"])
    parser.add_argument("--source", choices=list(BASES), required=True)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    run(args.action, args.backup, args.source)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        trace = error.__traceback__
        while trace and trace.tb_next:
            trace = trace.tb_next
        line = trace.tb_lineno if trace else 0
        print(
            f"Rollout 39 recusado: {type(error).__name__}, linha {line}. "
            "Preserve manutenção/backup/clone.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
