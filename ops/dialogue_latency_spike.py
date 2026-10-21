"""Spike de latência do parceiro de conversa (IA-45).

Mede, com turnos sintéticos derivados do próprio seed, o tempo de ida e volta ao
provedor de diálogo e quantas respostas sobrevivem ao saneamento. Não toca em
banco, não grava nada e nunca envia dado de aluno: o texto do "aluno" sai das
frases da aula, com palavras removidas para provocar checks reprovados.

Provedores:

- `mock`     valida o harness sem rede (latência simulada);
- `ollama`   API local `/api/chat` com `format` = JSON Schema (desenvolvimento);
- `gateway`  POST JSON `{messages, schema}` com Bearer do ambiente, resposta
             `{result: {...}, cost_microusd?: int}`; contrato a confirmar no BE-46.

Uso: uv run --project backend python -m ops.dialogue_latency_spike --provider mock --turns 30
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.services import dialogue_prompts as dp

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seed" / "lessons.json"
Provider = Callable[[list[dict[str, str]], dict[str, Any]], tuple[object, int | None]]


def load_brief(course: str, lesson: int) -> dp.LessonBrief:
    lessons = json.loads(SEED.read_text(encoding="utf-8"))
    match = next(x for x in lessons if x["course_slug"] == course and x["number"] == lesson)
    return dp.brief_from_seed(match)


def synthetic_turns(
    brief: dp.LessonBrief, count: int, seed: int
) -> list[tuple[str, list[dp.CheckCode]]]:
    """Frases da aula, algumas degradadas, com os códigos que a camada determinística daria."""

    rng = random.Random(seed)
    phrases = list(brief.phrases) or [f"I like {brief.title}."]
    turns: list[tuple[str, list[dp.CheckCode]]] = []
    for index in range(count):
        base = phrases[index % len(phrases)]
        kind = index % 4
        if kind == 0:
            turns.append((base, []))
        elif kind == 1:
            words = base.split()
            turns.append((" ".join(words[:2]), ["too_short"]))
        elif kind == 2:
            turns.append((base, ["target_terms_missing"]))
        else:
            turns.append(
                (" ".join(rng.sample(base.split(), len(base.split()))), ["grammar_pattern_missing"])
            )
    return turns


def percentile(values: Sequence[float], share: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    index = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
    return ordered[index]


def mock_provider(seed: int) -> Provider:
    rng = random.Random(seed)

    def call(messages: list[dict[str, str]], schema: dict[str, Any]) -> tuple[object, int | None]:
        time.sleep(rng.uniform(0.05, 0.25))
        allowed = schema["properties"]["hints"]["items"]["properties"]["code"]["enum"]
        hints = (
            []
            if allowed == ["__none__"]
            else [{"code": allowed[0], "message": "Tente usar o vocabulário da aula."}]
        )
        return {
            "partner_text": "That sounds fun! Do you go by bus or by taxi?",
            "hints": hints,
            "confidence": 0.8,
        }, 0

    return call


def ollama_provider(base_url: str, model: str, timeout: float) -> Provider:
    def call(messages: list[dict[str, str]], schema: dict[str, Any]) -> tuple[object, int | None]:
        body = json.dumps(
            {
                "model": model,
                "messages": messages,
                "stream": False,
                "format": schema,
                "options": {"temperature": 0},
            }
        ).encode()
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
        content = payload.get("message", {}).get("content", "")
        try:
            return json.loads(content), None
        except ValueError:
            return content, None

    return call


def gateway_provider(url: str, token: str | None, timeout: float) -> Provider:
    def call(messages: list[dict[str, str]], schema: dict[str, Any]) -> tuple[object, int | None]:
        body = json.dumps({"messages": messages, "schema": schema}).encode()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
        cost = payload.get("cost_microusd")
        return payload.get("result", payload), (int(cost) if isinstance(cost, int) else None)

    return call


def run(
    provider: Provider, brief: dp.LessonBrief, turns: Sequence[tuple[str, list[dp.CheckCode]]]
) -> dict[str, Any]:
    latencies: list[float] = []
    valid = invalid = failures = 0
    cost_total = 0
    cost_known = 0
    history: list[tuple[str, str]] = []
    for transcript, failed in turns:
        messages = dp.turn_messages(brief, "guided", transcript, failed, history=history)  # type: ignore[arg-type]
        schema = dp.response_schema(failed)
        started = time.monotonic()
        try:
            raw, cost = provider(messages, schema)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            failures += 1
            latencies.append(time.monotonic() - started)
            continue
        latencies.append(time.monotonic() - started)
        turn = dp.sanitize_provider_output(raw, failed)
        if turn is None:
            invalid += 1
            continue
        valid += 1
        if cost is not None:
            cost_total += cost
            cost_known += 1
        history.append(("student", transcript))
        history.append(("partner", turn.partner_text))
    return {
        "prompt_version": dp.PROMPT_VERSION,
        "turns": len(turns),
        "valid": valid,
        "invalid_output": invalid,
        "transport_failures": failures,
        "latency_p50_s": round(percentile(latencies, 0.5), 3),
        "latency_p95_s": round(percentile(latencies, 0.95), 3),
        "latency_max_s": round(max(latencies), 3) if latencies else None,
        "latency_mean_s": round(statistics.fmean(latencies), 3) if latencies else None,
        "cost_microusd_total": cost_total if cost_known else None,
        "cost_known_turns": cost_known,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=("mock", "ollama", "gateway"), default="mock")
    parser.add_argument("--turns", type=int, default=30)
    parser.add_argument("--course", default="voa-level-1")
    parser.add_argument("--lesson", type=int, default=31)
    parser.add_argument("--seed", type=int, default=44)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--base-url", default=os.environ.get("ASSIST_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    )
    parser.add_argument("--model", default=os.environ.get("ASSIST_OLLAMA_MODEL", "qwen2.5:7b"))
    parser.add_argument("--gateway-url", default=os.environ.get("ASSIST_DIALOGUE_URL", ""))
    parser.add_argument(
        "--token-env", default="ASSIST_PROVIDER_TOKEN", help="nome da variável com o Bearer"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    brief = load_brief(args.course, args.lesson)
    turns = synthetic_turns(brief, args.turns, args.seed)
    if args.provider == "mock":
        provider = mock_provider(args.seed)
    elif args.provider == "ollama":
        provider = ollama_provider(args.base_url, args.model, args.timeout)
    else:
        if not args.gateway_url:
            print(
                "Informe --gateway-url ou ASSIST_DIALOGUE_URL para o provedor gateway.",
                file=sys.stderr,
            )
            return 2
        provider = gateway_provider(args.gateway_url, os.environ.get(args.token_env), args.timeout)
    report = run(provider, brief, turns)
    report.update({"provider": args.provider, "lesson": f"{args.course}/{args.lesson}"})
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        r = report
        print(f"provedor={r['provider']} aula={r['lesson']} prompt={r['prompt_version']}")
        print(
            f"turnos={r['turns']} válidos={r['valid']} inválidos={r['invalid_output']} "
            f"falhas={r['transport_failures']}"
        )
        print(
            f"latência s: p50={r['latency_p50_s']} p95={r['latency_p95_s']} "
            f"máx={r['latency_max_s']} média={r['latency_mean_s']}"
        )
        print(
            f"custo microUSD: {r['cost_microusd_total']} "
            f"({r['cost_known_turns']} turnos com custo)"
        )
    return 0 if report["valid"] == report["turns"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
