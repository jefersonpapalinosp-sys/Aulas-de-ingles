"""Servidor local comprova que token/corpo não acompanham redirecionamentos."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.services import assistance


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_gateway_does_not_follow_redirects(status):
    received = []

    class Redirect(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, self.headers.get("Authorization")))
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(status)
            self.send_header("Location", f"http://localhost:{self.server.server_port}/sink")
            self.end_headers()

        def do_GET(self):
            received.append((self.path, self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Redirect) as server:
        runner = threading.Thread(target=server.serve_forever, daemon=True)
        runner.start()
        try:
            with pytest.raises(assistance.ProviderFailure, match="provider_unavailable"):
                assistance._post_json(
                    f"http://127.0.0.1:{server.server_port}/redirect",
                    b"synthetic-body",
                    content_type="application/json",
                    token="synthetic-secret",
                    timeout=2,
                )
        finally:
            server.shutdown()
            runner.join(timeout=5)
    assert received == [("/redirect", "Bearer synthetic-secret")]
