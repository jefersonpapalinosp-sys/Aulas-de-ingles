"""Alinha apenas dev b84 -> 39A; exige backup, restore e ensaio da mesma imagem.

Não para/inicia serviços, não executa seed e não aceita origem de estudo/produção.
Em falha, preserve a manutenção e os artefatos; não faça downgrade nem restore in-place.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ops import concurrency_rollout, recovery, study_rollout
from ops.recovery_archive import (
    audio_inventory,
    file_info,
    require,
    verify_bundle,
    write_json,
)

BASE = "b84e2c7a9d31"
HEAD = "e17b5fad0264"
NEW_TABLES = (
    *concurrency_rollout.NEW_TABLES,
    "study_activity_session",
    "study_activity_event",
    "study_active_interval",
)
NEW_COLUMNS = {
    **concurrency_rollout.NEW_COLUMNS,
    "writing_feedback": ["algorithm_version", "rubric_version", "rubric_snapshot"],
    "media_progress": [
        "revision",
        "completed",
        "operation_key",
        "fingerprint",
        "changed_at",
    ],
    "study_plan": ["timezone"],
}


def fingerprints(target):
    return study_rollout.fingerprints(
        target, excluded_columns=NEW_COLUMNS, excluded_tables=NEW_TABLES
    )


def image_id():
    return json.loads(recovery.docker("image", "inspect", recovery.HELPER))[0]["Id"]


def validate_manifest(manifest):
    require(
        manifest["source"]["kind"] == "dev" and manifest["source"]["project"] == "aulas-ingles",
        "Exige backup do desenvolvimento; estudo/produção não são aceitos.",
    )
    require(manifest["snapshot"]["revision"] == [BASE], "Revisão de origem não prevista.")


def run_migration(target, tools_image, *, head=HEAD, clone=recovery.DEV_CHECK):
    require(
        (head, clone) in {(HEAD, recovery.DEV_CHECK), ("f28c6abe1375", recovery.ASSIST_CHECK)},
        "Par revisão/clone não previsto.",
    )
    require(
        target == clone or target == recovery.source_target("dev"),
        "Migration permitida apenas no clone dedicado ou no desenvolvimento confirmado.",
    )
    recovery.check_target(target)
    recovery.quiet(target)
    if target == clone:
        url = (
            "postgresql+asyncpg://aulas_restore:restore_disposable_only"
            f"@{clone.service}:5432/aulas_ingles_restore"
        )
    else:
        env = recovery.env_of(recovery.container("aulas-ingles", "api"))
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
            "Conexão do migrador não corresponde ao desenvolvimento confirmado.",
        )
    # Arquivo temporário privado; não colocar credenciais no argv nem nos recibos.
    with tempfile.NamedTemporaryFile(mode="w", prefix="aulas-dev-migration-") as envfile:
        envfile.write(f"DATABASE_URL={url}\nAPP_ENV=dev\nASSISTED_FEATURES_ENABLED=false\n")
        envfile.flush()
        for command in (
            ("alembic", "upgrade", head),
            ("alembic", "upgrade", head),
            ("alembic", "check"),
        ):
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
                envfile.name,
                "--entrypoint",
                command[0],
                tools_image,
                *command[1:],
                timeout=300,
            )


def verify_initial_state(target):
    concurrency_rollout.verify_new_state(target)
    for table in NEW_TABLES:
        require(
            recovery.query(target, f"SELECT count(*) FROM {table}") == 0,
            "Tabelas novas contêm eventos não previstos.",
        )
    for sql in (
        (
            "SELECT count(*) FROM writing_feedback WHERE algorithm_version != 'legacy-v1' "
            "OR rubric_version IS NOT NULL OR rubric_snapshot IS NOT NULL"
        ),
        (
            "SELECT count(*) FROM media_progress WHERE revision != 0 OR completed "
            "OR operation_key IS NOT NULL OR fingerprint IS NOT NULL OR changed_at IS NOT NULL"
        ),
        "SELECT count(*) FROM study_plan WHERE timezone != 'UTC'",
    ):
        require(
            recovery.query(target, sql) == 0,
            "Estado inicial inesperado nas colunas novas.",
        )


def verify_voice(target, manifest):
    with tempfile.TemporaryDirectory(prefix="aulas-dev-voice-") as directory:
        path = Path(directory) / "voice.tar"
        with path.open("xb") as stream:
            recovery.voice(target, "export", stdout=stream)
        require(audio_inventory(path) == manifest["audio_files"], "Voz divergiu do backup.")


def validate_receipt(receipt, *, manifest_hash, tools_image):
    require(
        receipt.get("verified") is True
        and receipt.get("revision") == HEAD
        and receipt.get("target") == recovery.CONFIRM_DEV_CHECK
        and receipt.get("manifest") == manifest_hash
        and receipt.get("tools_image") == tools_image,
        "Ensaio da mesma imagem, backup e clone não comprovado.",
    )


def run(action, backup):
    require(action in {"capture", "rehearse", "apply"}, "Ação não prevista.")
    manifest = verify_bundle(backup)
    validate_manifest(manifest)
    source = recovery.source_target("dev")
    source_info = recovery.check_target(source)
    recovery.quiet(source)
    require(
        manifest["source"]["database"] == source.database
        and manifest["source"]["db_container_id"] == source_info["Id"]
        and manifest["source"]["voice_volume"] == source.voice_volume,
        "Backup pertence a outra origem.",
    )
    manifest_hash = file_info(backup / "manifest.json")
    tools_image = image_id()
    prefix = f"dev39-{manifest['bundle_id']}"
    capture_path = recovery.BACKUPS / f"{prefix}-capture.json"
    rehearsal_path = recovery.BACKUPS / f"{prefix}-rehearse.json"
    with recovery.lease("dev-alignment"):
        require(
            recovery.query(source, recovery.SNAPSHOT_SQL) == manifest["snapshot"],
            "Origem mudou após o backup; não aplicar.",
        )
        if action == "capture":
            audit = concurrency_rollout.audit(source)
            verify_voice(source, manifest)
            write_json(
                capture_path,
                {
                    "manifest": manifest_hash,
                    "tools_image": tools_image,
                    "tables": fingerprints(source),
                    "audit": audit,
                },
            )
            print("Captura privada concluída; sem textos pessoais ou credenciais nos logs.")
            return
        proof = concurrency_rollout.private_json(capture_path)
        require(
            proof["manifest"] == manifest_hash and proof["tools_image"] == tools_image,
            "Backup ou imagem mudou após captura; exige novo ensaio.",
        )
        require(
            fingerprints(source) == proof["tables"],
            "Dados da origem mudaram após captura.",
        )
        concurrency_rollout.audit(source, expected=proof["audit"])
        verify_voice(source, manifest)
        if action == "rehearse":
            restored = concurrency_rollout.private_json(
                recovery.BACKUPS / "restore-receipts" / f"{manifest['bundle_id']}.json"
            )
            require(
                restored.get("verified") is True
                and restored.get("bundle_id") == manifest["bundle_id"]
                and restored.get("target") == recovery.CONFIRM_DEV_CHECK
                and restored.get("manifest") == manifest_hash,
                "Restore no clone dedicado não comprovado.",
            )
            target = recovery.DEV_CHECK
        else:
            validate_receipt(
                concurrency_rollout.private_json(rehearsal_path),
                manifest_hash=manifest_hash,
                tools_image=tools_image,
            )
            target = source
        recovery.check_target(target)
        recovery.quiet(target)
        require(
            recovery.query(target, recovery.SNAPSHOT_SQL) == manifest["snapshot"],
            "Destino não corresponde ao backup de origem.",
        )
        require(fingerprints(target) == proof["tables"], "Conteúdo do destino diverge.")
        verify_voice(target, manifest)
        run_migration(target, tools_image)
        recovery.quiet(target)
        require(
            recovery.query(target, recovery.SNAPSHOT_SQL)
            == {**manifest["snapshot"], "revision": [HEAD]},
            "Snapshot pós-migration diverge.",
        )
        require(
            fingerprints(target) == proof["tables"],
            "Dados históricos divergiram; não reabrir.",
        )
        verify_initial_state(target)
        concurrency_rollout.audit(target, expected=proof["audit"])
        verify_voice(target, manifest)
        write_json(
            recovery.BACKUPS / f"{prefix}-{action}.json",
            {
                "verified": True,
                "manifest": manifest_hash,
                "tools_image": tools_image,
                "revision": HEAD,
                "target": recovery.CONFIRM_DEV_CHECK if action == "rehearse" else "aulas-ingles/db",
                "tables": len(proof["tables"]),
                "rows": sum(table["count"] for table in proof["tables"].values()),
                "audio_count": len(manifest["audio_files"]),
                "audit": proof["audit"],
            },
        )
        print(f"{action}: {len(proof['tables'])} tabelas históricas e voz preservadas; {HEAD}.")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "rehearse", "apply"])
    parser.add_argument("--backup", required=True, type=Path)
    args = parser.parse_args()
    run(args.action, args.backup)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Alinhamento dev não aprovado. Preserve manutenção, backup e clone; "
            "não faça restore sobre a origem.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
