"""Ensaio dirigido e prova de preservação; nunca migra produção automaticamente."""

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

from ops import recovery, roles
from ops.recovery_archive import (
    RecoveryError,
    audio_inventory,
    file_info,
    require,
    verify_bundle,
    write_json,
)

HEAD = "c95f3d8ba042"


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


def clone_run(*command: str) -> bytes:
    target = recovery.STUDY_CHECK
    recovery.check_target(target)
    recovery.quiet(target)
    with tempfile.NamedTemporaryFile(mode="w", prefix="aulas-study-clone-") as env:
        env.write("APP_ENV=dev\nASSISTED_FEATURES_ENABLED=false\n")
        env.write(
            "DATABASE_URL=postgresql+asyncpg://aulas_restore:restore_disposable_only@study-check-db:5432/aulas_ingles_restore\n"
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


def run(action: str, backup: Path) -> None:
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
        clone_run("alembic", "upgrade", HEAD)
        clone_run("python", "-m", "app.cli", "writing-rubrics")
        clone_run("python", "-m", "app.cli", "writing-rubrics")  # idempotência real
    require(
        fingerprints(target) == tables, "Dados históricos divergiram; não liberar tráfego."
    )
    require(
        json_object(recovery.query(target, recovery.SNAPSHOT_SQL)).get("revision") == [HEAD],
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
            "revision": HEAD,
            "manifest": proof["manifest"],
            "audio_count": len(audio_files),
        },
    )
    print(
        f"{action}: {len(tables)} tabelas preservadas; rubricas e voz conferidas."
    )


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "rehearse", "verify"])
    parser.add_argument("--backup", required=True, type=Path)
    args = parser.parse_args()
    run(args.action, args.backup)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Rollout não aprovado; preserve os artefatos e não libere tráfego.", file=sys.stderr)
        raise SystemExit(1) from None
