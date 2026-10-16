"""Alinhamento DEV 39F: backup, clone exclusivo, preservação e recibo obrigatório.

Não inicia/para aplicações, não semeia, não restaura sobre a origem e não faz downgrade.
Falha mantém a manutenção; preserve o backup e o clone para diagnóstico.
"""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from ops import concurrency_rollout, dev_alignment, recovery, study_rollout
from ops.recovery_archive import RecoveryError, file_info, require, verify_bundle, write_json

BASE = "e17b5fad0264"
HEAD = "f28c6abe1375"
NEW_COLUMNS = {
    "writing_feedback": ["assist_reservation_id"],
    "transcription_job": ["assist_reservation_id"],
}
SMOKE_SCRIPT = recovery.ROOT / "ops" / "assist_alignment_smoke.py"


def fingerprints(target):
    return study_rollout.fingerprints(
        target, excluded_columns=NEW_COLUMNS, excluded_tables=("assist_reservation",)
    )


def validate_manifest(manifest):
    require(
        manifest["source"]["kind"] == "dev" and manifest["source"]["project"] == "aulas-ingles",
        "Exige backup do desenvolvimento; estudo/produção não são aceitos.",
    )
    require(manifest["snapshot"]["revision"] == [BASE], "Revisão de origem não prevista.")


def verify_backfill(target):
    # EXCEPT ALL nos dois sentidos verifica também duplicatas, ausências, vínculos,
    # custo desconhecido, datas e ausência de despacho inventado. Zero é válido.
    sql = """
    WITH expected AS (
      SELECT f.assist_reservation_id AS id, f.user_id,
        'legacy-writing:' || f.id AS request_key, repeat('0',64) AS fingerprint,
        'writing' AS modality, 'legacy-writing:' || f.id AS provider_key,
        'consumed' AS state, 'legacy_observed' AS reason,
        f.assisted_cost_microusd AS cost_microusd,
        f.analysis_mode = 'assisted' AND f.assisted_cost_microusd > 0 AS cost_known,
        f.created_at, f.created_at + interval '15 minutes' AS expires_at,
        NULL::timestamptz AS dispatched_at
      FROM writing_feedback f WHERE f.provider IS NOT NULL
      UNION ALL
      SELECT j.assist_reservation_id, j.user_id, 'legacy-transcription:' || j.id,
        repeat('0',64), 'transcription', j.idempotency_key, 'consumed', 'legacy_observed',
        j.cost_microusd, j.status = 'completed' AND j.cost_microusd > 0,
        j.requested_at, j.requested_at + interval '15 minutes', NULL::timestamptz
      FROM transcription_job j
    ), actual AS (
      SELECT id, user_id, request_key, fingerprint, modality, provider_key, state,
        reason, cost_microusd, cost_known, created_at, expires_at, dispatched_at
      FROM assist_reservation
    ), difference AS (
      (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)
      UNION ALL
      (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
    )
    SELECT (SELECT count(*) FROM difference) +
      (SELECT count(*) FROM writing_feedback
       WHERE provider IS NULL AND assist_reservation_id IS NOT NULL)
    """
    require(
        recovery.query(target, sql) == 0,
        "Backfill diverge dos registros legados observáveis.",
    )


def validate_receipt(receipt, *, manifest_hash, tools_image):
    require(
        receipt.get("verified") is True
        and receipt.get("revision") == HEAD
        and receipt.get("target") == recovery.CONFIRM_ASSIST_CHECK
        and receipt.get("manifest") == manifest_hash
        and receipt.get("tools_image") == tools_image,
        "Ensaio da mesma imagem, backup e clone não comprovado.",
    )


def validate_smoke_receipt(receipt, *, manifest_hash, tools_image):
    validate_receipt(receipt, manifest_hash=manifest_hash, tools_image=tools_image)
    require(
        receipt.get("smoke_script") == file_info(SMOKE_SCRIPT)
        and receipt.get("http")
        == {
            "verified": True,
            "mode": "http-clone",
            "checks": 11,
            "synthetic_user_remaining": 0,
            "provider_calls": 0,
        },
        "Smoke HTTP da mesma versão não comprovado.",
    )


def smoke_clone(backup):
    manifest = verify_bundle(backup)
    validate_manifest(manifest)
    manifest_hash = file_info(backup / "manifest.json")
    tools_image = dev_alignment.image_id()
    prefix = f"dev39f-{manifest['bundle_id']}"
    receipt = concurrency_rollout.private_json(recovery.BACKUPS / f"{prefix}-rehearse.json")
    validate_receipt(receipt, manifest_hash=manifest_hash, tools_image=tools_image)
    proof = concurrency_rollout.private_json(recovery.BACKUPS / f"{prefix}-capture.json")
    require(
        proof["manifest"] == manifest_hash and proof["tools_image"] == tools_image,
        "Captura de outro backup/imagem.",
    )
    target = recovery.ASSIST_CHECK
    recovery.check_target(target)
    recovery.quiet(target)
    with recovery.lease("dev-alignment"):
        require(fingerprints(target) == proof["tables"], "Clone divergiu antes do smoke.")
        require(
            recovery.query(target, recovery.SNAPSHOT_SQL)
            == {**manifest["snapshot"], "revision": [HEAD]},
            "Revisão inesperada no clone.",
        )
        verify_backfill(target)
        smoke_receipt_path = recovery.BACKUPS / f"{prefix}-smoke.json"
        if smoke_receipt_path.exists():
            validate_smoke_receipt(
                concurrency_rollout.private_json(smoke_receipt_path),
                manifest_hash=manifest_hash,
                tools_image=tools_image,
            )
            dev_alignment.verify_voice(target, manifest)
            print("Recibo HTTP existente reconferido; nenhum smoke repetido.")
            return
        with tempfile.NamedTemporaryFile(mode="w", prefix="aulas-assist-clone-") as envfile:
            envfile.write(
                "DATABASE_URL=postgresql+asyncpg://aulas_restore:restore_disposable_only"
                "@assist-check-db:5432/aulas_ingles_restore\nAPP_ENV=dev\n"
                "ASSISTED_FEATURES_ENABLED=false\nLOG_LEVEL=warning\n"
            )
            envfile.flush()
            container_id = (
                recovery.docker(
                    "run",
                    "-d",
                    "--name",
                    "aulas-39f-clone-smoke-api",
                    "--read-only",
                    "--user",
                    "10001:10001",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--network",
                    f"{recovery.PROJECT}_default",
                    "--env-file",
                    envfile.name,
                    "--entrypoint",
                    "uvicorn",
                    tools_image,
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
                        container_id,
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
            with SMOKE_SCRIPT.open("rb") as script:
                result = json.loads(
                    recovery.docker(
                        "exec", "-i", container_id, "python", "-", stdin=script, timeout=90
                    )
                )
        finally:
            # Apenas o container efêmero criado acima; sem volumes nem portas.
            recovery.docker("stop", container_id, timeout=30)
            recovery.docker("rm", container_id)
        recovery.quiet(target)
        require(fingerprints(target) == proof["tables"], "Histórico mudou no smoke.")
        verify_backfill(target)
        dev_alignment.verify_voice(target, manifest)
        receipt = {**receipt, "smoke_script": file_info(SMOKE_SCRIPT), "http": result}
        validate_smoke_receipt(receipt, manifest_hash=manifest_hash, tools_image=tools_image)
        write_json(recovery.BACKUPS / f"{prefix}-smoke.json", receipt)
        print("Smoke HTTP no clone: 11 verificações; dados preservados; nenhum provedor chamado.")


def run(action, backup):
    require(action in {"capture", "rehearse", "apply"}, "Ação não prevista.")
    manifest = verify_bundle(backup)
    validate_manifest(manifest)
    source = recovery.source_target("dev")
    info = recovery.check_target(source)
    recovery.quiet(source)
    require(
        manifest["source"]["database"] == source.database
        and manifest["source"]["db_container_id"] == info["Id"]
        and manifest["source"]["voice_volume"] == source.voice_volume,
        "Backup pertence a outra origem.",
    )
    manifest_hash = file_info(backup / "manifest.json")
    tools_image = dev_alignment.image_id()
    prefix = f"dev39f-{manifest['bundle_id']}"
    capture_path = recovery.BACKUPS / f"{prefix}-capture.json"
    with recovery.lease("dev-alignment"):
        require(
            recovery.query(source, recovery.SNAPSHOT_SQL) == manifest["snapshot"],
            "Origem mudou após backup; não aplicar.",
        )
        dev_alignment.verify_voice(source, manifest)
        if action == "capture":
            write_json(
                capture_path,
                {
                    "manifest": manifest_hash,
                    "tools_image": tools_image,
                    "tables": fingerprints(source),
                },
            )
            print("Captura privada 39F concluída; sem conteúdo pessoal nos logs.")
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
        if action == "rehearse":
            receipt = concurrency_rollout.private_json(
                recovery.BACKUPS / "restore-receipts" / f"{manifest['bundle_id']}.json"
            )
            require(
                receipt.get("verified") is True
                and receipt.get("bundle_id") == manifest["bundle_id"]
                and receipt.get("target") == recovery.CONFIRM_ASSIST_CHECK
                and receipt.get("manifest") == manifest_hash,
                "Restore no clone 39F dedicado não comprovado.",
            )
            target = recovery.ASSIST_CHECK
        else:
            validate_receipt(
                concurrency_rollout.private_json(recovery.BACKUPS / f"{prefix}-rehearse.json"),
                manifest_hash=manifest_hash,
                tools_image=tools_image,
            )
            validate_smoke_receipt(
                concurrency_rollout.private_json(recovery.BACKUPS / f"{prefix}-smoke.json"),
                manifest_hash=manifest_hash,
                tools_image=tools_image,
            )
            target = source
        recovery.check_target(target)
        recovery.quiet(target)
        require(
            recovery.query(target, recovery.SNAPSHOT_SQL) == manifest["snapshot"]
            and fingerprints(target) == proof["tables"],
            "Destino diverge da origem capturada.",
        )
        dev_alignment.verify_voice(target, manifest)
        dev_alignment.run_migration(target, tools_image, head=HEAD, clone=recovery.ASSIST_CHECK)
        recovery.quiet(target)
        require(
            recovery.query(target, recovery.SNAPSHOT_SQL)
            == {**manifest["snapshot"], "revision": [HEAD]}
            and fingerprints(target) == proof["tables"],
            "Dados históricos divergiram; não reabrir.",
        )
        verify_backfill(target)
        dev_alignment.verify_voice(target, manifest)
        result = {
            "verified": True,
            "manifest": manifest_hash,
            "tools_image": tools_image,
            "revision": HEAD,
            "target": recovery.CONFIRM_ASSIST_CHECK if action == "rehearse" else "aulas-ingles/db",
            "tables": len(proof["tables"]),
            "rows": sum(t["count"] for t in proof["tables"].values()),
            "audio_count": len(manifest["audio_files"]),
            "legacy_reservations": recovery.query(
                target, "SELECT count(*) FROM assist_reservation"
            ),
        }
        write_json(recovery.BACKUPS / f"{prefix}-{action}.json", result)
        print(
            f"{action}: {result['tables']} tabelas / {result['rows']} linhas preservadas; {HEAD}."
        )


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "rehearse", "smoke", "apply"])
    parser.add_argument("--backup", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "smoke":
        smoke_clone(args.backup)
    else:
        run(args.action, args.backup)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Alinhamento 39F não aprovado; preserve manutenção, backup e clone.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
