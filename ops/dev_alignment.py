"""Alinha apenas dev b84 -> 39A; exige backup, restore e ensaio da mesma imagem.

Não para/inicia serviços, não executa seed e não aceita origem de estudo/produção.
Em falha, preserve a manutenção e os artefatos; não faça downgrade nem restore in-place.
"""

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ops import recovery, rollout
from ops.recovery_archive import (
    FileInfo,
    RecoveryError,
    audio_inventory,
    file_info,
    require,
    verify_bundle,
    write_json,
)

BASE = "b84e2c7a9d31"
HEAD = "e17b5fad0264"
NEW_TABLES = (
    *rollout.NEW_TABLES,
    "study_activity_session",
    "study_activity_event",
    "study_active_interval",
)
NEW_COLUMNS = {
    **rollout.NEW_COLUMNS,
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


def fingerprints(target: recovery.Target) -> dict[str, rollout.Fingerprint]:
    return rollout.fingerprints(
        target, excluded_columns=NEW_COLUMNS, excluded_tables=NEW_TABLES
    )


def image_id() -> str:
    images: object = json.loads(recovery.docker("image", "inspect", recovery.HELPER))
    if not isinstance(images, list) or len(images) != 1:
        raise RecoveryError("Imagem de ferramentas ausente ou ambígua.")
    identity = rollout.json_object(images[0]).get("Id")
    if not isinstance(identity, str) or not identity:
        raise RecoveryError("Identidade da imagem de ferramentas inválida.")
    return identity


def validate_manifest(manifest: Mapping[str, object]) -> None:
    source = rollout.json_object(manifest.get("source"))
    snapshot = rollout.json_object(manifest.get("snapshot"))
    require(
        source.get("kind") == "dev" and source.get("project") == "aulas-ingles",
        "Exige backup do desenvolvimento; estudo/produção não são aceitos.",
    )
    require(snapshot.get("revision") == [BASE], "Revisão de origem não prevista.")


def run_migration(
    target: recovery.Target,
    tools_image: str,
    *,
    head: str = HEAD,
    clone: recovery.Target = recovery.DEV_CHECK,
) -> None:
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


def verify_initial_state(target: recovery.Target) -> None:
    rollout.verify_new_state(target)
    for table in NEW_TABLES:
        require(
            rollout.query_count(target, f"SELECT count(*) FROM {table}") == 0,
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
            rollout.query_count(target, sql) == 0,
            "Estado inicial inesperado nas colunas novas.",
        )


def verify_voice(target: recovery.Target, manifest: Mapping[str, object]) -> None:
    with tempfile.TemporaryDirectory(prefix="aulas-dev-voice-") as directory:
        path = Path(directory) / "voice.tar"
        with path.open("xb") as stream:
            recovery.voice(target, "export", stdout=stream)
        require(audio_inventory(path) == manifest["audio_files"], "Voz divergiu do backup.")


def validate_receipt(
    receipt: Mapping[str, object], *, manifest_hash: FileInfo, tools_image: str
) -> None:
    require(
        receipt.get("verified") is True
        and receipt.get("revision") == HEAD
        and receipt.get("target") == recovery.CONFIRM_DEV_CHECK
        and receipt.get("manifest") == manifest_hash
        and receipt.get("tools_image") == tools_image,
        "Ensaio da mesma imagem, backup e clone não comprovado.",
    )


def run(action: str, backup: Path) -> None:
    require(action in {"capture", "rehearse", "apply"}, "Ação não prevista.")
    manifest = verify_bundle(backup)
    validate_manifest(manifest)
    origin = rollout.json_object(manifest["source"])
    snapshot = rollout.json_object(manifest["snapshot"])
    audio_files = rollout.json_object(manifest.get("audio_files"))
    source = recovery.source_target("dev")
    source_info = recovery.check_target(source)
    recovery.quiet(source)
    require(
        origin.get("database") == source.database
        and origin.get("db_container_id") == source_info["Id"]
        and origin.get("voice_volume") == source.voice_volume,
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
            audit = rollout.audit(source)
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
        proof = rollout.private_json(capture_path)
        tables = rollout.checked_fingerprints(proof.get("tables"))
        expected_audit = rollout.checked_audit(proof.get("audit"))
        require(
            proof["manifest"] == manifest_hash and proof["tools_image"] == tools_image,
            "Backup ou imagem mudou após captura; exige novo ensaio.",
        )
        require(
            fingerprints(source) == tables,
            "Dados da origem mudaram após captura.",
        )
        rollout.audit(source, expected=expected_audit)
        verify_voice(source, manifest)
        if action == "rehearse":
            restored = rollout.private_json(
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
                rollout.private_json(rehearsal_path),
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
        require(fingerprints(target) == tables, "Conteúdo do destino diverge.")
        verify_voice(target, manifest)
        run_migration(target, tools_image)
        recovery.quiet(target)
        require(
            recovery.query(target, recovery.SNAPSHOT_SQL)
            == {**snapshot, "revision": [HEAD]},
            "Snapshot pós-migration diverge.",
        )
        require(
            fingerprints(target) == tables,
            "Dados históricos divergiram; não reabrir.",
        )
        verify_initial_state(target)
        rollout.audit(target, expected=expected_audit)
        verify_voice(target, manifest)
        write_json(
            recovery.BACKUPS / f"{prefix}-{action}.json",
            {
                "verified": True,
                "manifest": manifest_hash,
                "tools_image": tools_image,
                "revision": HEAD,
                "target": recovery.CONFIRM_DEV_CHECK if action == "rehearse" else "aulas-ingles/db",
                "tables": len(tables),
                "rows": sum(table["count"] for table in tables.values()),
                "audio_count": len(audio_files),
                "audit": proof["audit"],
            },
        )
        print(f"{action}: {len(tables)} tabelas históricas e voz preservadas; {HEAD}.")


def main() -> None:
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
