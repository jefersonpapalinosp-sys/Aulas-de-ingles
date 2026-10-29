"""Ensaios históricos parametrizados; nunca migram a origem automaticamente.

Perfis study (Sprint 37) e concurrency (38) mantêm revisões e recibos fixos.
Não usar como upgrade genérico: o release vigente segue operacao_local.md.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypedDict

from app.db.concurrency_audit import RULES

from ops import recovery, roles
from ops.recovery_archive import (
    RecoveryError,
    audio_inventory,
    file_info,
    require,
    verify_bundle,
    write_json,
)

STUDY_HEAD = "c95f3d8ba042"
CONCURRENCY_BASE = "c95f3d8ba042"
CONCURRENCY_HEAD = "d06a4e9cb153"
NEW_TABLES = ("review_event", "auth_rate_bucket")
LEGACY_JOURNEY_RULES = {"study_completion_timestamp", "study_step_consistency"}
NEW_COLUMNS = {
    "writing_draft": ["revision"],
    "study_session_progress": ["revision"],
    "review_item": ["revision"],
    "refresh_session": ["family_id", "successor_jti"],
}


class Fingerprint(TypedDict):
    count: int
    sha256: str


def json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RecoveryError("Metadados devem ser um objeto JSON.")
    return dict(value)


def checked_count(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RecoveryError("Contagem inválida; esperado inteiro não negativo.")
    return value


def query_count(target: recovery.Target, sql: str) -> int:
    return checked_count(recovery.query(target, sql))


def checked_fingerprints(value: object) -> dict[str, Fingerprint]:
    result: dict[str, Fingerprint] = {}
    for name, item in json_object(value).items():
        require(re.fullmatch("[a-z_]+", name) is not None, "Tabela não prevista.")
        row = json_object(item)
        require(set(row) == {"count", "sha256"}, "Prova de tabela incompleta ou inesperada.")
        digest = row["sha256"]
        if not isinstance(digest, str) or re.fullmatch("[a-f0-9]{64}", digest) is None:
            raise RecoveryError("Hash de tabela inválido.")
        result[name] = {"count": checked_count(row["count"]), "sha256": digest}
    return result


def fingerprints(
    target: recovery.Target,
    *,
    excluded_columns: Mapping[str, Sequence[str]] | None = None,
    excluded_tables: Sequence[str] = (),
) -> dict[str, Fingerprint]:
    tables: object = recovery.query(
        target,
        """
        SELECT json_agg(tablename ORDER BY tablename)
        FROM pg_tables WHERE schemaname='public' AND tablename != 'alembic_version'
    """,
    )
    if not isinstance(tables, list) or not all(isinstance(name, str) for name in tables):
        raise RecoveryError("Inventário de tabelas inválido.")
    require(len(tables) == len(set(tables)), "Inventário de tabelas duplicado.")
    result: dict[str, Fingerprint] = {}
    if excluded_columns is None:
        excluded_columns = {
            "writing_prompt": ["requirements"],
            "writing_feedback": ["algorithm_version", "rubric_version", "rubric_snapshot"],
        }
    for name in tables:
        require(re.fullmatch("[a-z_]+", name) is not None, "Tabela não prevista.")
        if name in excluded_tables:
            continue
        excluded = excluded_columns.get(name, [])
        require(
            all(
                isinstance(column, str) and re.fullmatch("[a-z_][a-z0-9_]*", column)
                for column in excluded
            ),
            "Coluna inválida.",
        )
        expression = "to_jsonb(t)" + "".join(f" - '{column}'" for column in excluded)
        # Nada do resultado bruto é impresso/persistido; somente hashes e contagens.
        rows: object = recovery.query(
            target, f"SELECT coalesce(json_agg({expression}), '[]') FROM public.{name} t"
        )
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise RecoveryError("Conteúdo de tabela inválido para prova de preservação.")
        canonical = sorted(
            json.dumps(row, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
            for row in rows
        )
        result[name] = {
            "count": len(rows),
            "sha256": hashlib.sha256("\n".join(canonical).encode()).hexdigest(),
        }
    return result


def clone_run(*command: str, profile: str) -> bytes:
    require(profile in {"study", "concurrency"}, "Perfil inválido.")
    target = recovery.STUDY_CHECK if profile == "study" else recovery.CONCURRENCY_CHECK
    recovery.check_target(target)
    recovery.quiet(target)
    with tempfile.NamedTemporaryFile(mode="w", prefix=f"aulas-{profile}-clone-") as env:
        env.write("APP_ENV=dev\nASSISTED_FEATURES_ENABLED=false\n")
        env.write(
            "DATABASE_URL=postgresql+asyncpg://aulas_restore:restore_disposable_only"
            f"@{target.service}:5432/aulas_ingles_restore\n"
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


def concurrency_fingerprints(target: recovery.Target) -> dict[str, Fingerprint]:
    return fingerprints(target, excluded_columns=NEW_COLUMNS, excluded_tables=NEW_TABLES)


def checked_audit(value: object) -> dict[str, int]:
    report = json_object(value)
    require(set(report) == set(RULES), "Regras da auditoria divergem.")
    return {rule: checked_count(count) for rule, count in report.items()}


def audit(
    target: recovery.Target, *, preserve_legacy: bool = False, expected: object = None
) -> dict[str, int]:
    if expected is not None:
        expected = checked_audit(expected)
    report = {name: query_count(target, sql) for name, sql in RULES.items()}
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


def private_json(path: Path) -> dict[str, object]:
    require(
        path.is_file()
        and not path.is_symlink()
        and not path.parent.is_symlink()
        and path.stat().st_mode & 0o077 == 0,
        "Prova privada ausente ou inválida.",
    )
    try:
        return json_object(json.loads(path.read_text()))
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
            query_count(target, f"SELECT count(*) FROM {table}") == 0,
            "Eventos novos antes da reabertura; recuse histórico inventado.",
        )
    for table in ("writing_draft", "study_session_progress", "review_item"):
        require(
            query_count(target, f"SELECT count(*) FROM {table} WHERE revision != 0") == 0,
            "Revisão inicial inesperada.",
        )
    require(
        query_count(
            target,
            "SELECT count(*) FROM refresh_session WHERE "
            "family_id != jti OR successor_jti IS NOT NULL",
        )
        == 0,
        "Família inicial inesperada.",
    )


def _run_study(action: str, backup: Path) -> None:
    require(action in {"capture", "rehearse", "verify"}, "Ação inválida.")
    manifest = verify_bundle(backup)
    origin = json_object(manifest.get("source"))
    audio_files = json_object(manifest.get("audio_files"))
    require(origin.get("kind") == "prod", "Exige pacote da base de estudo.")
    source = recovery.source_target("prod")
    require(origin.get("database") == source.database, "Origem divergente.")
    recovery.check_target(source)
    recovery.quiet(source)
    proof_path = recovery.BACKUPS / f"rollout-{manifest['bundle_id']}.json"
    if action == "capture":
        roles.backup_gate(roles.target("prod"), backup)
        require(not proof_path.exists() and not proof_path.is_symlink(), "Prova já existe.")
        write_json(
            proof_path,
            {
                "manifest": file_info(backup / "manifest.json"),
                "tables": fingerprints(source),
            },
        )
        print("Prova privada capturada; nenhum texto, token ou hash de senha exposto.")
        return
    require(
        proof_path.is_file()
        and not proof_path.is_symlink()
        and not proof_path.parent.is_symlink()
        and proof_path.stat().st_mode & 0o077 == 0,
        "Prova privada ausente.",
    )
    proof = json_object(json.loads(proof_path.read_text()))
    tables = checked_fingerprints(proof.get("tables"))
    require(proof["manifest"] == file_info(backup / "manifest.json"), "Prova de outro pacote.")
    target = recovery.STUDY_CHECK if action == "rehearse" else source
    recovery.check_target(target)
    recovery.quiet(target)
    if action == "rehearse":
        require(
            recovery.query(target, recovery.SNAPSHOT_SQL) == manifest["snapshot"],
            "Clone diverge do backup.",
        )
        require(fingerprints(target) == tables, "Conteúdo restaurado diverge.")
        clone_run("alembic", "upgrade", STUDY_HEAD, profile="study")
        clone_run("python", "-m", "app.cli", "writing-rubrics", profile="study")
        clone_run(
            "python", "-m", "app.cli", "writing-rubrics", profile="study"
        )  # idempotência real
    require(fingerprints(target) == tables, "Dados históricos divergiram; não liberar tráfego.")
    require(
        json_object(recovery.query(target, recovery.SNAPSHOT_SQL)).get("revision") == [STUDY_HEAD],
        "Schema não atualizado.",
    )
    with tempfile.TemporaryDirectory(prefix="aulas-voice-proof-") as directory:
        path = Path(directory) / "voice.tar"
        with path.open("xb") as stream:
            recovery.voice(target, "export", stdout=stream)
        require(audio_inventory(path) == manifest["audio_files"], "Voz diverge do backup.")
    receipt = recovery.BACKUPS / f"{action}-{manifest['bundle_id']}.json"
    write_json(
        receipt,
        {
            "verified": True,
            "tables": len(tables),
            "revision": STUDY_HEAD,
            "manifest": proof["manifest"],
            "audio_count": len(audio_files),
        },
    )
    print(f"{action}: {len(tables)} tabelas preservadas; rubricas e voz conferidas.")


def _run_concurrency(action: str, backup: Path, *, preserve_legacy: bool = False) -> None:
    require(action in {"capture", "rehearse", "verify"}, "Ação inválida.")
    manifest = verify_bundle(backup)
    origin = json_object(manifest.get("source"))
    snapshot = json_object(manifest.get("snapshot"))
    require(origin.get("kind") == "prod", "Exige backup do ambiente de estudo.")
    require(snapshot.get("revision") == [CONCURRENCY_BASE], "Backup não está no schema esperado.")
    audio_files = json_object(manifest.get("audio_files"))
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
                "tables": concurrency_fingerprints(source),
                "audit": report,
                "preserve_legacy": preserve_legacy,
            },
        )
        print("Prova pré-migration capturada sem conteúdo pessoal.")
        return
    proof = private_json(proof_path)
    tables = checked_fingerprints(proof.get("tables"))
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
        require(concurrency_fingerprints(target) == tables, "Conteúdo restaurado diverge.")
        audit(target, preserve_legacy=preserve_legacy, expected=expected_audit)
        clone_run("alembic", "upgrade", CONCURRENCY_HEAD, profile="concurrency")
        clone_run("alembic", "upgrade", CONCURRENCY_HEAD, profile="concurrency")
    else:
        receipt = private_json(rehearsal_path)
        require(
            receipt.get("verified") is True
            and receipt.get("revision") == CONCURRENCY_HEAD
            and receipt.get("manifest") == manifest_hash,
            "Ensaio da migration não comprovado.",
        )
    require(concurrency_fingerprints(target) == tables, "Dados históricos divergiram; não reabrir.")
    require(
        json_object(recovery.query(target, recovery.SNAPSHOT_SQL)).get("revision")
        == [CONCURRENCY_HEAD],
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
            "revision": CONCURRENCY_HEAD,
            "manifest": manifest_hash,
            "audio_count": len(audio_files),
            "audit": proof["audit"],
            "preserve_legacy": preserve_legacy,
        },
    )
    print(
        f"{action}: {len(tables)} tabelas históricas e voz preservadas; schema {CONCURRENCY_HEAD}."
    )


def run(action: str, backup: Path, *, profile: str, preserve_legacy: bool = False) -> None:
    require(profile in {"study", "concurrency"}, "Perfil inválido.")
    require(action in {"capture", "rehearse", "verify"}, "Ação inválida.")
    require(
        profile == "concurrency" or not preserve_legacy, "Política de legado exige concurrency."
    )
    if profile == "study":
        _run_study(action, backup)
    else:
        _run_concurrency(action, backup, preserve_legacy=preserve_legacy)


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=["study", "concurrency"])
    parser.add_argument("action", choices=["capture", "rehearse", "verify"])
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument(
        "--preserve-legacy-journeys",
        action="store_true",
        help="Preserva e documenta somente divergências preexistentes de jornada; "
        "exige hashes e contagens idênticos antes/depois, sem reparo.",
    )
    args = parser.parse_args()
    run(
        args.action,
        args.backup,
        profile=args.profile,
        preserve_legacy=args.preserve_legacy_journeys,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Ensaio não aprovado; preserve os artefatos e não libere tráfego.", file=sys.stderr)
        raise SystemExit(1) from None
