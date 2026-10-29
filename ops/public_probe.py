"""Probe externo de disponibilidade do domínio público (INFRA-46).

Roda **de fora** da VM de propósito: um probe que mora no mesmo host não
distingue "a aplicação caiu" de "a rede do host caiu", e é justamente essa a
diferença que interessa a quem é acordado de madrugada.

O que ele afirma, em ordem: o domínio resolve e aceita TLS; `/api/health`
responde 200 com `status` e `schema` compatíveis; a borda não devolve o
cabeçalho `Server` com versão; a resposta chega dentro do limite de tempo. Não
precisa de credencial — `/api/health` é público — e por isso pode rodar em
qualquer runner sem segredo nenhum.

Nada do que ele imprime carrega URL completa, corpo de resposta ou cabeçalho:
um log de CI é público, e um probe que vaza a topologia da instalação troca um
problema por outro.
"""

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

State = Literal["ok", "critical"]

# Acima disto o aluno já sentiu. O limite é generoso para um probe externo, que
# carrega latência de rede do runner até a VM.
MAX_LATENCY_MS = 5_000
TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Probe:
    name: str
    state: State
    observed: int | float | str | None
    expected: int | float | str
    action: str


def _probe(
    name: str,
    good: bool,
    observed: int | float | str | None,
    expected: int | float | str,
    action: str,
) -> Probe:
    return Probe(name, "ok" if good else "critical", observed, expected, action)


def public_url(base: str) -> str:
    """Só HTTPS, sem credencial, sem query e sem fragmento."""
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("O domínio público precisa ser uma URL HTTPS.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("A URL do probe não pode ter credencial, query ou fragmento.")
    return base.rstrip("/") + "/api/health"


def fetch(url: str) -> tuple[int, dict[str, Any], str, int]:
    """Devolve status, corpo, cabeçalho `Server` e latência em ms."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    context = ssl.create_default_context()
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=context) as response:
            status = int(response.status)
            server = str(response.headers.get("Server") or "")
            payload = response.read(100_001)
    except urllib.error.HTTPError as error:
        status = int(error.code)
        server = str(error.headers.get("Server") or "") if error.headers else ""
        payload = error.read(100_001)
    latency_ms = round((time.monotonic() - started) * 1000)
    if len(payload) > 100_000:
        raise ValueError("Resposta do domínio público excedeu o limite.")
    try:
        body = json.loads(payload)
    except json.JSONDecodeError:
        body = {}
    return status, body if isinstance(body, dict) else {}, server, latency_ms


def evaluate(status: int, body: dict[str, Any], server: str, latency_ms: int) -> dict[str, Any]:
    exposes_details = any(
        field in body for field in ("version", "env", "schema_current", "schema_required")
    )
    probes = [
        _probe(
            "health_status_code",
            status == 200,
            status,
            200,
            "Conferir a borda e o container da API antes de qualquer migration.",
        ),
        _probe(
            "health_payload",
            body.get("status") == "ok" and body.get("schema") == "compatible",
            body.get("schema") or body.get("status") or "sem corpo",
            "status=ok e schema=compatible",
            "Imagem e migration desalinhadas: alinhar sem downgrade destrutivo.",
        ),
        _probe(
            "health_hides_details",
            not exposes_details,
            "detalhes expostos" if exposes_details else "sem detalhes",
            "sem versão, ambiente ou revisões",
            "Usar readiness autenticada para diagnóstico; corrigir a exposição na rota pública.",
        ),
        _probe(
            "edge_hides_version",
            # `server_tokens off` (SEC-45) deixa "nginx" sem versão. Qualquer
            # dígito aqui é regressão da borda.
            not any(caractere.isdigit() for caractere in server),
            "com versão" if any(c.isdigit() for c in server) else "sem versão",
            "sem versão",
            "Restaurar `server_tokens off` na borda; a versão exposta facilita "
            "a escolha de exploit.",
        ),
        _probe(
            "latency_ms",
            latency_ms <= MAX_LATENCY_MS,
            latency_ms,
            f"<= {MAX_LATENCY_MS}",
            "Conferir carga da VM e o healthcheck do worker antes de concluir que é a rede.",
        ),
    ]
    overall = "critical" if any(item.state == "critical" for item in probes) else "ok"
    return {"status": overall, "probes": [asdict(item) for item in probes]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="https://dominio-publico")
    args = parser.parse_args(argv)
    try:
        url = public_url(args.base_url)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        report = evaluate(*fetch(url))
    except Exception:
        # Sem URL, sem corpo, sem cabeçalho: o log do CI é público.
        print("Probe do domínio público falhou antes de avaliar.", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
