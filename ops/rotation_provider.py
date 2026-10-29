"""Gateway sintético em loopback: sobreposição e revogação de tokens sem logs."""

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from app.services.assistance import ProviderFailure, call_writing_provider


def rehearse_provider() -> dict[str, int | bool]:
    old, new = secrets.token_hex(32), secrets.token_hex(32)
    accepted = {old}
    statuses: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            allowed = self.headers.get("Authorization", "").removeprefix("Bearer ") in accepted
            status = 200 if allowed else 401
            statuses.append(status)
            body = json.dumps(
                {
                    "summary": "Synthetic rotation probe",
                    "suggestions": [],
                    "confidence": 1.0,
                    "cost_microusd": 0,
                }
                if allowed
                else {"error": "unauthorized"}
            ).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/writing"

    def call(token: str) -> None:
        result = call_writing_provider(url, "Synthetic text.", [], token=token, timeout=3)
        if result.cost_microusd != 0:
            raise RuntimeError("Gateway sintético retornou custo inesperado.")

    try:
        call(old)
        accepted.add(new)
        call(new)
        call(old)  # consumidor antigo durante sobreposição
        accepted.remove(old)
        try:
            call(old)
        except ProviderFailure as error:
            if error.code != "provider_unavailable":
                raise RuntimeError("Falha do gateway não foi sanitizada.") from None
        else:
            raise RuntimeError("Token revogado continuou autorizado.")
        call(new)
        if statuses != [200, 200, 200, 401, 200]:
            raise RuntimeError("Sequência de rotação do gateway divergiu.")
        return {"overlap_ok": True, "old_revoked": True, "new_ok": True, "calls": 5}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
