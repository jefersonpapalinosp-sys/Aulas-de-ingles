"""Sprint 38: ensaio em clone novo e prova de preservação, sem migrar a origem."""

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from app.db.concurrency_audit import RULES

from ops import recovery, study_rollout
from ops.recovery_archive import (
    RecoveryError,
    audio_inventory,
    file_info,
    require,
    verify_bundle,
    write_json,
)

BASE = "c95f3d8ba042"
HEAD = "d06a4e9cb153"
NEW_TABLES = ("review_event", "auth_rate_bucket")
LEGACY_JOURNEY_RULES = {"study_completion_timestamp", "study_step_consistency"}
NEW_COLUMNS = {
    "writing_draft": ["revision"],
    "study_session_progress": ["revision"],
    "review_item": ["revision"],
    "refresh_session": ["family_id", "successor_jti"],
}


def fingerprints(target: recovery.Target) -> dict[str, study_rollout.Fingerprint]:
    return study_rollout.fingerprints(
        target, excluded_columns=NEW_COLUMNS, excluded_tables=NEW_TABLES
    )


def checked_audit(value: object) -> dict[str, int]:
    report = study_rollout.json_object(value)
    require(set(report) == set(RULES), "Regras da auditoria divergem.")
    return {rule: study_rollout.checked_count(count) for rule, count in report.items()}


def audit(
    target: recovery.Target, *, preserve_legacy: bool = False, expected: object = None
) -> dict[str, int]:
    if expected is not None:
        expected = checked_audit(expected)
    report = {name: study_rollout.query_count(target, sql) for name, sql in RULES.items()}
    # Apenas regra/contagem, sem textos, IDs pessoais ou credenciais.
    print(json.dumps({"audit": report}, sort_keys=True))
    allowed = LEGACY_JOURNEY_RULES if preserve_legacy else set()
    require(
        not any(count for rule, count in report.items() if rule not in allowed),
        "Auditoria recusada; decidir divergências sem reparo automático.",
    )
    if expected is not None:
        require(report == expected, "Auditoria mudou durante o rollout; não reabrir.")
    return report


def clone_run(*command: str) -> bytes:
    target = recovery.CONCURRENCY_CHECK
    recovery.check_target(target)
    recovery.quiet(target)
    with tempfile.NamedTemporaryFile(mode="w", prefix="aulas-concurrency-clone-") as env:
        env.write("APP_ENV=dev\nASSISTED_FEATURES_ENABLED=false\n")
        env.write(
            "DATABASE_URL=postgresql+asyncpg://aulas_restore:restore_disposable_only"
            "@concurrency-check-db:5432/aulas_ingles_restore\n"
        )
        env.flush()
        return recovery.docker(
            "run",
            "--rm",
            "--network",
            f"{target.project}_default",
            "--env-file",
            env.name,
            recovery.HELPER,
            *command,
            timeout=300,
        )


def private_json(path: Path) -> dict[str, object]:
    require(
        path.is_file()
        and not path.is_symlink()
        and not path.parent.is_symlink()
        and path.stat().st_mode & 0o077 == 0,
        "Prova privada ausente ou inválida.",
    )
    try:
        return study_rollout.json_object(json.loads(path.read_text()))
    except (ValueError, OSError) as exc:
        raise RecoveryError("Prova privada ilegível ou inválida.") from exc


def validate_restore(backup: Path, manifest: Mapping[str, object]) -> None:
    result = private_json(recovery.BACKUPS / "restore-receipts" / f"{manifest['bundle_id']}.json")
    require(
        result.get("verified") is True
        and result.get("bundle_id") == manifest["bundle_id"]
        and result.get("target") == recovery.CONFIRM_CONCURRENCY_CHECK
        and result.get("manifest") == file_info(backup / "manifest.json"),
        "Recibo não comprova restore no clone da Sprint 38.",
    )


def verify_new_state(target: recovery.Target) -> None:
    for table in NEW_TABLES:
        require(
            study_rollout.query_count(target, f"SELECT count(*) FROM {table}") == 0,
            "Eventos novos antes da reabertura; recuse histórico inventado.",
        )
    for table in ("writing_draft", "study_session_progress", "review_item"):
        require(
            study_rollout.query_count(target, f"SELECT count(*) FROM {table} WHERE revision != 0")
            == 0,
            "Revisão inicial inesperada.",
        )
    require(
        study_rollout.query_count(
            target,
            "SELECT count(*) FROM refresh_session WHERE "
            "family_id != jti OR successor_jti IS NOT NULL",
        )
        == 0,
        "Família inicial inesperada.",
    )


def run(action: str, backup: Path, *, preserve_legacy: bool = False) -> None:
    require(action in {"capture", "rehearse", "verify"}, "Ação inválida.")
    manifest = verify_bundle(backup)
    origin = study_rollout.json_object(manifest.get("source"))
    snapshot = study_rollout.json_object(manifest.get("snapshot"))
    require(origin.get("kind") == "prod", "Exige backup do ambiente de estudo.")
    require(snapshot.get("revision") == [BASE], "Backup não está no schema esperado.")
    audio_files = study_rollout.json_object(manifest.get("audio_files"))
    source = recovery.source_target("prod")
    require(origin.get("database") == source.database, "Origem divergente.")
    recovery.check_target(source)
    recovery.quiet(source)
    validate_restore(backup, manifest)
    proof_path = recovery.BACKUPS / f"sprint38-capture-{manifest['bundle_id']}.json"
    rehearsal_path = recovery.BACKUPS / f"sprint38-rehearse-{manifest['bundle_id']}.json"
    manifest_hash = file_info(backup / "manifest.json")
    if action == "capture":
        require(
            recovery.query(source, recovery.SNAPSHOT_SQL) == manifest["snapshot"],
            "Origem mudou após backup.",
        )
        report = audit(source, preserve_legacy=preserve_legacy)
        write_json(
            proof_path,
            {
                "manifest": manifest_hash,
                "tables": fingerprints(source),
                "audit": report,
                "preserve_legacy": preserve_legacy,
            },
        )
        print("Prova pré-migration capturada sem conteúdo pessoal.")
        return
    proof = private_json(proof_path)
    tables = study_rollout.checked_fingerprints(proof.get("tables"))
    expected_audit = checked_audit(proof.get("audit"))
    require(proof["manifest"] == manifest_hash, "Prova de outro backup.")
    require(proof["preserve_legacy"] is preserve_legacy, "Política de legado diverge da captura.")
    target = recovery.CONCURRENCY_CHECK if action == "rehearse" else source
    recovery.check_target(target)
    recovery.quiet(target)
    if action == "rehearse":
        require(
            recovery.query(target, recovery.SNAPSHOT_SQL) == manifest["snapshot"],
            "Clone não corresponde ao backup.",
        )
        require(fingerprints(target) == tables, "Conteúdo restaurado diverge.")
        audit(target, preserve_legacy=preserve_legacy, expected=expected_audit)
        clone_run("alembic", "upgrade", HEAD)
        clone_run("alembic", "upgrade", HEAD)
    else:
        receipt = private_json(rehearsal_path)
        require(
            receipt.get("verified") is True
            and receipt.get("revision") == HEAD
            and receipt.get("manifest") == manifest_hash,
            "Ensaio da migration não comprovado.",
        )
    require(fingerprints(target) == tables, "Dados históricos divergiram; não reabrir.")
    require(
        study_rollout.json_object(recovery.query(target, recovery.SNAPSHOT_SQL)).get("revision")
        == [HEAD],
        "Schema não atualizado.",
    )
    verify_new_state(target)
    audit(target, preserve_legacy=preserve_legacy, expected=expected_audit)
    with tempfile.TemporaryDirectory(prefix="aulas-concurrency-voice-") as directory:
        path = Path(directory) / "voice.tar"
        with path.open("xb") as stream:
            recovery.voice(target, "export", stdout=stream)
        require(audio_inventory(path) == manifest["audio_files"], "Voz diverge do backup.")
    write_json(
        recovery.BACKUPS / f"sprint38-{action}-{manifest['bundle_id']}.json",
        {
            "verified": True,
            "tables": len(tables),
            "revision": HEAD,
            "manifest": manifest_hash,
            "audio_count": len(audio_files),
            "audit": proof["audit"],
            "preserve_legacy": preserve_legacy,
        },
    )
    print(f"{action}: {len(tables)} tabelas históricas e voz preservadas; schema {HEAD}.")


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "rehearse", "verify"])
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument(
        "--preserve-legacy-journeys",
        action="store_true",
        help="Preserva e documenta somente divergências preexistentes de jornada; "
        "exige hashes e contagens idênticos antes/depois, sem reparo.",
    )
    args = parser.parse_args()
    run(args.action, args.backup, preserve_legacy=args.preserve_legacy_journeys)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Sprint 38 não aprovada; preserve os artefatos e não libere tráfego.", file=sys.stderr
        )
        raise SystemExit(1) from None
