"""Gate de readiness e métricas com limites, ação e responsável explícitos."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

State = Literal["ok", "warning", "critical"]


@dataclass(frozen=True)
class Thresholds:
    minimum_requests: int = 20
    maximum_error_rate: float = 0.05
    maximum_queue_age_seconds: int = 300
    maximum_worker_age_seconds: int = 60
    maximum_maintenance_age_seconds: int = 7200
    maximum_waiting_locks: int = 0
    minimum_media_free_bytes: int = 1_073_741_824


@dataclass(frozen=True)
class Check:
    name: str
    state: State
    observed: int | float | str | None
    threshold: int | float | str
    owner: str
    action: str


def _check(
    name: str,
    good: bool,
    observed: int | float | str | None,
    threshold: int | float | str,
    owner: str,
    action: str,
) -> Check:
    return Check(name, "ok" if good else "critical", observed, threshold, owner, action)


def evaluate(
    readiness: dict[str, Any], metrics: dict[str, Any], thresholds: Thresholds
) -> dict[str, Any]:
    requests = metrics["requests"]
    queue = metrics["transcription_queue"]
    database = metrics["database"]
    media = metrics["media"]
    deletions = metrics["account_deletions"]
    legacy_review = metrics["legacy_review"]
    total = int(requests["requests_total"])
    failures = int(requests["responses_5xx_total"])
    error_rate = failures / total if total else 0.0
    checks = [
        _check(
            "readiness_schema",
            readiness.get("status") == "ok" and readiness.get("schema") == "compatible",
            readiness.get("schema"),
            "compatible",
            "release manager",
            "Manter o tráfego bloqueado e alinhar imagem/migration; "
            "não executar downgrade destrutivo.",
        ),
        _check(
            "request_error_rate",
            total < thresholds.minimum_requests
            or error_rate <= thresholds.maximum_error_rate,
            round(error_rate, 6),
            f"<= {thresholds.maximum_error_rate} após {thresholds.minimum_requests} requests",
            "backend on-call",
            "Correlacionar request-id, preservar respostas pendentes e "
            "reverter somente a aplicação se necessário.",
        ),
        _check(
            "queue_age_seconds",
            queue["oldest_queued_seconds"] is None
            or int(queue["oldest_queued_seconds"])
            <= thresholds.maximum_queue_age_seconds,
            queue["oldest_queued_seconds"],
            f"<= {thresholds.maximum_queue_age_seconds}",
            "worker on-call",
            "Verificar heartbeat/provedor; manter correção local disponível e "
            "não reenviar jobs manualmente.",
        ),
        _check(
            "worker_age_seconds",
            queue["worker_age_seconds"] is not None
            and int(queue["worker_age_seconds"])
            <= thresholds.maximum_worker_age_seconds,
            queue["worker_age_seconds"],
            f"<= {thresholds.maximum_worker_age_seconds}",
            "worker on-call",
            "Inspecionar logs agregados e reiniciar o worker; jobs duráveis serão retomados.",
        ),
        _check(
            "maintenance_age_seconds",
            queue.get("maintenance_age_seconds") is not None
            and int(queue["maintenance_age_seconds"])
            <= thresholds.maximum_maintenance_age_seconds,
            queue.get("maintenance_age_seconds"),
            f"<= {thresholds.maximum_maintenance_age_seconds}",
            "worker on-call",
            "Manter tráfego bloqueado e conferir heartbeat/último lote de retenção; "
            "não executar limpeza manual sem política.",
        ),
        _check(
            "waiting_locks",
            int(database["waiting_locks"]) <= thresholds.maximum_waiting_locks,
            int(database["waiting_locks"]),
            f"<= {thresholds.maximum_waiting_locks}",
            "database operator",
            "Identificar bloqueio sem imprimir SQL/parâmetros e pausar o deploy até liberar.",
        ),
        _check(
            "account_deletion_failures",
            int(deletions["failed"]) == 0,
            int(deletions["failed"]),
            "= 0",
            "privacy owner",
            "Preservar recibos anônimos e reprocessar a limpeza de arquivos pelo worker.",
        ),
        _check(
            "legacy_review_reconciliation",
            int(legacy_review["unlinked_cards"]) == 0
            and int(legacy_review["mismatched_links"]) == 0,
            int(legacy_review["unlinked_cards"])
            + int(legacy_review["mismatched_links"]),
            "= 0",
            "database operator",
            "Manter review_card e o tráfego bloqueados; reconciliar no clone a ligação "
            "com review_item sem excluir histórico.",
        ),
        _check(
            "media_free_bytes",
            bool(media["filesystem_available"])
            and int(media["filesystem_free_bytes"] or 0)
            >= thresholds.minimum_media_free_bytes,
            media["filesystem_free_bytes"],
            f">= {thresholds.minimum_media_free_bytes}",
            "storage operator",
            "Bloquear novos uploads, preservar arquivos referenciados e "
            "ampliar/limpar apenas pela política de retenção.",
        ),
    ]
    overall = "critical" if any(item.state == "critical" for item in checks) else "ok"
    return {"status": overall, "checks": [asdict(item) for item in checks]}


def _url(base: str, path: str) -> str:
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.query:
        raise ValueError("Base URL HTTP(S) inválida.")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Base URL não pode conter credencial ou fragmento.")
    return base.rstrip("/") + path


def fetch(base: str, path: str, *, token: str | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(_url(base, path), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = response.read(1_000_001)
    except urllib.error.HTTPError as error:
        payload = error.read(1_000_001)
    if len(payload) > 1_000_000:
        raise ValueError("Resposta operacional excedeu o limite.")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Resposta operacional inválida.")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    args = parser.parse_args(argv)
    token = os.environ.get("OPERATIONS_TOKEN")
    if not token:
        print("OPERATIONS_TOKEN ausente; gate não executado.", file=sys.stderr)
        return 2
    try:
        report = evaluate(
            fetch(args.base_url, "/api/health"),
            fetch(args.base_url, "/api/operations/metrics", token=token),
            Thresholds(),
        )
    except Exception:
        print(
            "Gate operacional falhou sem expor URL, resposta ou credencial.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
