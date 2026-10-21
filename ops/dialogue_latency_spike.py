"""Spike de latência do parceiro de conversa (IA-45).

Mede, com turnos sintéticos derivados do próprio seed, o tempo de ida e volta ao
provedor de diálogo (e, opcionalmente, ao de transcrição) e quantas respostas
sobrevivem ao saneamento. Não toca em banco, não grava nada e nunca envia dado
de aluno: o texto do "aluno" sai das frases da aula, com palavras removidas para
provocar checks reprovados; o áudio da transcrição é um WAV sintético de ruído
baixo, só para medir transporte e processamento.

Provedores de diálogo (`--provider`):

- `mock`        valida o harness sem rede (latência simulada);
- `ollama`      API local `/api/chat` com `format` = JSON Schema (desenvolvimento);
- `gateway`     POST JSON `{messages, schema}` com Bearer do ambiente, resposta
                `{result: {...}, cost_microusd?: int}`; contrato a confirmar no BE-46;
- `cloudflare`  Workers AI (`/ai/run/<modelo>`) com `response_format` json_schema;
                lê `usage.neurons` da resposta para o orçamento diário gratuito.

Transcrição (`--stt`): `none`, `mock` ou `cloudflare` (Whisper no Workers AI).
O critério 2 do ADR é p95 do turno completo (STT + modelo) abaixo de 8 s.

Uso: uv run --project backend python -m ops.dialogue_latency_spike --provider mock --turns 30
     set -a; source secrets/cloudflare-workers-ai.env; set +a
     uv run --project backend python -m ops.dialogue_latency_spike \\
         --provider cloudflare --stt cloudflare --turns 30
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import os
import random
import statistics
import struct
import sys
import time
import urllib.error
import urllib.request
import wave
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.services import dialogue_prompts as dp

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seed" / "lessons.json"
Usage = dict[str, Any]
Provider = Callable[[list[dict[str, str]], dict[str, Any]], tuple[object, int | None, Usage | None]]
Stt = Callable[[bytes], tuple[str, Usage | None]]

CLOUDFLARE_API = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
CLOUDFLARE_CHAT_MODEL = "@cf/meta/llama-3.1-8b-instruct"
CLOUDFLARE_STT_MODEL = "@cf/openai/whisper-large-v3-turbo"
CLOUDFLARE_FREE_NEURONS_PER_DAY = 10_000
ADR_P95_BUDGET_S = 8.0


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


def synthetic_wav(seconds: float, seed: int = 1) -> bytes:
    """WAV mono 16 kHz/16 bit de ruído baixo: nada de voz real, só carga representativa."""

    rng = random.Random(seed)
    frames = int(16_000 * seconds)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as archive:
        archive.setnchannels(1)
        archive.setsampwidth(2)
        archive.setframerate(16_000)
        archive.writeframes(
            b"".join(struct.pack("<h", rng.randint(-300, 300)) for _ in range(frames))
        )
    return buffer.getvalue()


def percentile(values: Sequence[float], share: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    index = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
    return ordered[index]


def _stats(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"p50_s": None, "p95_s": None, "max_s": None, "mean_s": None}
    return {
        "p50_s": round(percentile(values, 0.5), 3),
        "p95_s": round(percentile(values, 0.95), 3),
        "max_s": round(max(values), 3),
        "mean_s": round(statistics.fmean(values), 3),
    }


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float) -> Any:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _post_bytes(url: str, data: bytes, headers: dict[str, str], timeout: float) -> Any:
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def mock_provider(seed: int) -> Provider:
    rng = random.Random(seed)

    def call(
        messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> tuple[object, int | None, Usage | None]:
        time.sleep(rng.uniform(0.05, 0.25))
        allowed = schema["properties"]["hints"]["items"]["properties"]["code"]["enum"]
        hints = (
            []
            if allowed == ["__none__"]
            else [{"code": allowed[0], "message": "Tente usar o vocabulário da aula."}]
        )
        raw = {
            "partner_text": "That sounds fun! Do you go by bus or by taxi?",
            "hints": hints,
            "confidence": 0.8,
        }
        return raw, 0, None

    return call


def mock_stt(seed: int) -> Stt:
    rng = random.Random(seed)

    def call(audio: bytes) -> tuple[str, Usage | None]:
        time.sleep(rng.uniform(0.05, 0.15))
        return "Thank you.", None

    return call


def ollama_provider(base_url: str, model: str, timeout: float) -> Provider:
    def call(
        messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> tuple[object, int | None, Usage | None]:
        payload = _post_json(
            f"{base_url.rstrip('/')}/api/chat",
            {
                "model": model,
                "messages": messages,
                "stream": False,
                "format": schema,
                "options": {"temperature": 0},
            },
            {"Content-Type": "application/json"},
            timeout,
        )
        content = payload.get("message", {}).get("content", "")
        try:
            return json.loads(content), None, None
        except ValueError:
            return content, None, None

    return call


def gateway_provider(url: str, token: str | None, timeout: float) -> Provider:
    def call(
        messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> tuple[object, int | None, Usage | None]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = _post_json(url, {"messages": messages, "schema": schema}, headers, timeout)
        cost = payload.get("cost_microusd")
        return payload.get("result", payload), (int(cost) if isinstance(cost, int) else None), None

    return call


def parse_cloudflare_chat(payload: Any) -> tuple[object, Usage | None]:
    """`result.response` vem como objeto (json_schema) ou string JSON; `usage.neurons` é o custo."""

    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return payload, None
    response = result.get("response")
    if isinstance(response, str):
        with contextlib.suppress(ValueError):
            response = json.loads(response)
    usage = result.get("usage")
    return response, usage if isinstance(usage, dict) else None


def cloudflare_provider(account_id: str, token: str, model: str, timeout: float) -> Provider:
    url = CLOUDFLARE_API.format(account=account_id, model=model)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    def call(
        messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> tuple[object, int | None, Usage | None]:
        payload = _post_json(
            url,
            {
                "messages": messages,
                "response_format": {"type": "json_schema", "json_schema": schema},
                "temperature": 0,
                "max_tokens": 200,
            },
            headers,
            timeout,
        )
        raw, usage = parse_cloudflare_chat(payload)
        return raw, None, usage

    return call


def cloudflare_stt(account_id: str, token: str, model: str, timeout: float) -> Stt:
    """Whisper no Workers AI: o turbo recebe JSON com base64; os demais, o áudio em bytes."""

    url = CLOUDFLARE_API.format(account=account_id, model=model)
    base64_json = "whisper-large-v3-turbo" in model

    def call(audio: bytes) -> tuple[str, Usage | None]:
        if base64_json:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
            payload = _post_json(url, {"audio": base64.b64encode(audio).decode()}, headers, timeout)
        else:
            headers = {
                "Content-Type": "application/octet-stream",
                "Authorization": f"Bearer {token}",
            }
            payload = _post_bytes(url, audio, headers, timeout)
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ValueError("resposta de transcrição sem result")
        usage = result.get("usage")
        return str(result.get("text") or ""), usage if isinstance(usage, dict) else None

    return call


def _neurons(usage: Usage | None) -> float | None:
    if not usage:
        return None
    value = usage.get("neurons")
    return float(value) if isinstance(value, int | float) else None


def run(
    provider: Provider,
    brief: dp.LessonBrief,
    turns: Sequence[tuple[str, list[dp.CheckCode]]],
    stt: Stt | None = None,
    audio: bytes | None = None,
) -> dict[str, Any]:
    llm_latencies: list[float] = []
    stt_latencies: list[float] = []
    total_latencies: list[float] = []
    valid = invalid = failures = stt_failures = 0
    cost_total = cost_known = 0
    neurons_total = 0.0
    neurons_known = 0
    prompt_tokens = completion_tokens = 0
    history: list[tuple[str, str]] = []
    for transcript, failed in turns:
        turn_started = time.monotonic()
        stt_elapsed = 0.0
        if stt is not None:
            stt_started = time.monotonic()
            try:
                _, stt_usage = stt(audio or b"")
                if (value := _neurons(stt_usage)) is not None:
                    neurons_total += value
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                stt_failures += 1
            stt_elapsed = time.monotonic() - stt_started
            stt_latencies.append(stt_elapsed)
        messages = dp.turn_messages(brief, "guided", transcript, failed, history=history)  # type: ignore[arg-type]
        schema = dp.response_schema(failed)
        llm_started = time.monotonic()
        try:
            raw, cost, usage = provider(messages, schema)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            failures += 1
            llm_latencies.append(time.monotonic() - llm_started)
            total_latencies.append(time.monotonic() - turn_started)
            continue
        llm_latencies.append(time.monotonic() - llm_started)
        total_latencies.append(time.monotonic() - turn_started)
        if (value := _neurons(usage)) is not None:
            neurons_total += value
            neurons_known += 1
        if usage:
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            completion_tokens += int(usage.get("completion_tokens") or 0)
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
    total = _stats(total_latencies)
    neurons_per_turn = (neurons_total / len(turns)) if neurons_known and turns else None
    return {
        "prompt_version": dp.PROMPT_VERSION,
        "turns": len(turns),
        "valid": valid,
        "invalid_output": invalid,
        "transport_failures": failures,
        "stt_failures": stt_failures,
        "llm": _stats(llm_latencies),
        "stt": _stats(stt_latencies) if stt is not None else None,
        "total": total,
        "p95_within_adr_budget": (
            total["p95_s"] is not None and float(total["p95_s"]) < ADR_P95_BUDGET_S
        ),
        "cost_microusd_total": cost_total if cost_known else None,
        "cost_known_turns": cost_known,
        "neurons_total": round(neurons_total, 3) if neurons_known else None,
        "neurons_per_turn": round(neurons_per_turn, 3) if neurons_per_turn is not None else None,
        "free_turns_per_day_estimate": (
            int(CLOUDFLARE_FREE_NEURONS_PER_DAY // neurons_per_turn) if neurons_per_turn else None
        ),
        "prompt_tokens": prompt_tokens or None,
        "completion_tokens": completion_tokens or None,
    }


def _render(report: dict[str, Any]) -> str:
    lines = [
        f"provedor={report['provider']} stt={report['stt_provider']} aula={report['lesson']} "
        f"prompt={report['prompt_version']} modelo={report['model']}",
        f"turnos={report['turns']} válidos={report['valid']} inválidos={report['invalid_output']} "
        f"falhas={report['transport_failures']} falhas_stt={report['stt_failures']}",
    ]
    for label in ("stt", "llm", "total"):
        stats = report.get(label)
        if stats:
            lines.append(
                f"{label:5} s: p50={stats['p50_s']} p95={stats['p95_s']} "
                f"máx={stats['max_s']} média={stats['mean_s']}"
            )
    lines.append(
        f"p95 do turno completo abaixo de {ADR_P95_BUDGET_S:.0f} s (critério 2 do ADR): "
        f"{'sim' if report['p95_within_adr_budget'] else 'não'}"
    )
    if report["neurons_total"] is not None:
        lines.append(
            f"neurons: total={report['neurons_total']} por turno={report['neurons_per_turn']} "
            f"→ cerca de {report['free_turns_per_day_estimate']} turnos/dia na cota gratuita"
        )
    if report["prompt_tokens"]:
        lines.append(
            f"tokens: prompt={report['prompt_tokens']} resposta={report['completion_tokens']}"
        )
    if report["cost_microusd_total"] is not None:
        lines.append(
            f"custo microUSD: {report['cost_microusd_total']} "
            f"({report['cost_known_turns']} turnos com custo)"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--provider", choices=("mock", "ollama", "gateway", "cloudflare"), default="mock"
    )
    parser.add_argument("--stt", choices=("none", "mock", "cloudflare"), default="none")
    parser.add_argument("--turns", type=int, default=30)
    parser.add_argument("--course", default="voa-level-1")
    parser.add_argument("--lesson", type=int, default=31)
    parser.add_argument("--seed", type=int, default=44)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--audio-seconds", type=float, default=8.0)
    parser.add_argument(
        "--base-url", default=os.environ.get("ASSIST_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    )
    parser.add_argument("--model", default=None, help="modelo de diálogo (padrão por provedor)")
    parser.add_argument("--stt-model", default=CLOUDFLARE_STT_MODEL)
    parser.add_argument("--gateway-url", default=os.environ.get("ASSIST_DIALOGUE_URL", ""))
    parser.add_argument("--token-env", default=None, help="nome da variável com o Bearer")
    parser.add_argument("--account-id-env", default="CLOUDFLARE_ACCOUNT_ID")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    brief = load_brief(args.course, args.lesson)
    turns = synthetic_turns(brief, args.turns, args.seed)
    model = args.model
    if args.provider == "mock":
        provider = mock_provider(args.seed)
        model = model or "mock"
    elif args.provider == "ollama":
        model = model or os.environ.get("ASSIST_OLLAMA_MODEL", "qwen2.5:7b")
        provider = ollama_provider(args.base_url, model, args.timeout)
    elif args.provider == "gateway":
        if not args.gateway_url:
            print(
                "Informe --gateway-url ou ASSIST_DIALOGUE_URL para o provedor gateway.",
                file=sys.stderr,
            )
            return 2
        token_env = args.token_env or "ASSIST_PROVIDER_TOKEN"
        provider = gateway_provider(args.gateway_url, os.environ.get(token_env), args.timeout)
        model = model or "gateway"
    else:
        token_env = args.token_env or "CLOUDFLARE_API_TOKEN"
        account_id = os.environ.get(args.account_id_env, "")
        token = os.environ.get(token_env, "")
        if not account_id or not token:
            print(
                f"Defina {args.account_id_env} e {token_env} no ambiente "
                "(sem imprimir valores) para o provedor cloudflare.",
                file=sys.stderr,
            )
            return 2
        model = model or CLOUDFLARE_CHAT_MODEL
        provider = cloudflare_provider(account_id, token, model, args.timeout)

    stt: Stt | None = None
    audio: bytes | None = None
    if args.stt != "none":
        audio = synthetic_wav(args.audio_seconds, args.seed)
        if args.stt == "mock":
            stt = mock_stt(args.seed)
        else:
            token_env = args.token_env or "CLOUDFLARE_API_TOKEN"
            account_id = os.environ.get(args.account_id_env, "")
            token = os.environ.get(token_env, "")
            if not account_id or not token:
                print(
                    f"Defina {args.account_id_env} e {token_env} no ambiente "
                    "para --stt cloudflare.",
                    file=sys.stderr,
                )
                return 2
            stt = cloudflare_stt(account_id, token, args.stt_model, args.timeout)

    report = run(provider, brief, turns, stt=stt, audio=audio)
    report.update(
        {
            "provider": args.provider,
            "stt_provider": args.stt,
            "model": model,
            "stt_model": args.stt_model if args.stt == "cloudflare" else args.stt,
            "audio_seconds": args.audio_seconds if args.stt != "none" else None,
            "lesson": f"{args.course}/{args.lesson}",
        }
    )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else _render(report))
    return 0 if report["valid"] == report["turns"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
