"""Provedor sintético exclusivo da rede E2E. Não acessa rede externa ou disco."""

import json
import os
import sys
import threading
import time
import urllib.request
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODES = {"success", "slow", "failure", "invalid"}
LOCK = threading.Lock()
STATE = {"stt": "success", "dialogue": "success"}
CALLS = {"stt": [], "dialogue": []}
ACTIVE = 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # Nem corpos, nem cabeçalhos, nem texto de teste vão para logs.

    def reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"fixture": "disposable-e2e"})
        if self.path == "/metrics":
            with LOCK:
                snapshot = {kind: list(calls) for kind, calls in CALLS.items()}
            return self.reply(200, snapshot)
        return self.reply(404, {})

    def do_POST(self):
        global ACTIVE
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2_000_000:
                return self.reply(413, {})
            body = self.rfile.read(length)
            if self.path == "/control":
                modes = json.loads(body)
                if set(modes) != set(STATE) or any(mode not in MODES for mode in modes.values()):
                    return self.reply(422, {})
                with LOCK:
                    if ACTIVE:
                        return self.reply(409, {"error": "in_flight"})
                    STATE.update(modes)
                    for calls in CALLS.values():
                        calls.clear()
                return self.reply(200, {"configured": True})
            kind = self.path.removeprefix("/")
            if kind not in STATE:
                return self.reply(404, {})
            key = self.headers.get("Idempotency-Key")
            content_type = self.headers.get("Content-Type", "")
            if not key or (kind == "stt" and not content_type.startswith("audio/")):
                return self.reply(422, {})
            if kind == "dialogue":
                payload = json.loads(body)
                if not payload.get("messages") or payload.get("temperature") != 0:
                    return self.reply(422, {})
                if payload["response_format"]["type"] != "json_schema":
                    return self.reply(422, {})
        except (ValueError, TypeError, KeyError):
            return self.reply(422, {})

        with LOCK:
            mode = STATE[kind]
            ACTIVE += 1
            CALLS[kind].append({"key": key, "bytes": length, "content_type": content_type})
        try:
            if mode == "slow":
                time.sleep(3)
            if mode == "failure":
                return self.reply(503, {"error": "synthetic_unavailable"})
            if mode == "invalid":
                return self.reply(200, {"unexpected": "synthetic_invalid_response"})
            if kind == "stt":
                return self.reply(
                    200,
                    {
                        "text": "The train is faster than the bus.",
                        "words": [
                            {
                                "text": word,
                                "start_ms": i * 100,
                                "end_ms": (i + 1) * 100,
                                "confidence": 0.6 if word == "train" else 0.98,
                            }
                            for i, word in enumerate(
                                ["The", "train", "is", "faster", "than", "the", "bus."]
                            )
                        ],
                        "cost_microusd": 3,
                    },
                )
            return self.reply(
                200,
                {
                    "result": {
                        "response": {
                            "partner_text": "What do you do after your trip?",
                            "hints": [],
                            "confidence": 0.9,
                        }
                    },
                    "cost_microusd": 7,
                },
            )
        finally:
            with LOCK:
                ACTIVE -= 1


if __name__ == "__main__":
    if os.environ.get("E2E_GATEWAY_ONLY") != "disposable-e2e":
        raise SystemExit("Gateway permitido somente no laboratório E2E.")
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if path not in {"control", "metrics", "health"}:
            raise SystemExit("Comando inválido")
        data = sys.argv[2].encode() if path == "control" else None
        request = urllib.request.Request(
            f"http://127.0.0.1:8080/{path}",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            print(response.read().decode())
    else:
        ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
