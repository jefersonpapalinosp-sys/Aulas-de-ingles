"""Transporte dos probes: limites, erros e saída sanitizada, sem chamadas de rede."""

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from ops import observability_check as operational
from ops import public_probe as public


def response(payload: bytes, status: int = 200) -> MagicMock:
    result = MagicMock()
    result.__enter__.return_value = result
    result.status = status
    result.headers = {"Server": "nginx"}
    result.read.return_value = payload
    return result


class PublicTransportTests(unittest.TestCase):
    def test_success_uses_tls_timeout_and_bounded_read(self) -> None:
        reply = response(b'{"status":"ok","schema":"compatible"}')
        with (
            patch.object(public.urllib.request, "urlopen", return_value=reply) as request,
            patch.object(public.time, "monotonic", side_effect=[10, 10.125]),
        ):
            status, body, server, latency = public.fetch("https://example.test/api/health")
        self.assertEqual((status, server, latency), (200, "nginx", 125))
        self.assertEqual(body["schema"], "compatible")
        reply.read.assert_called_once_with(100_001)
        self.assertEqual(request.call_args.kwargs["timeout"], public.TIMEOUT_SECONDS)
        self.assertTrue(request.call_args.kwargs["context"].check_hostname)
        self.assertIsNone(request.call_args.args[0].get_header("Authorization"))

    def test_http_error_is_evaluated_as_failure_with_its_status(self) -> None:
        headers = Message()
        headers["Server"] = "nginx"
        error = HTTPError("https://example.test", 503, "private", headers, io.BytesIO(b"{}"))
        self.addCleanup(error.close)
        with patch.object(public.urllib.request, "urlopen", side_effect=error):
            snapshot = public.fetch("https://example.test/api/health")
        self.assertEqual(snapshot[:3], (503, {}, "nginx"))
        self.assertEqual(public.evaluate(*snapshot)["status"], "critical")

    def test_invalid_json_and_non_objects_do_not_look_healthy(self) -> None:
        for payload in (b"private HTML", b"[]", b"null"):
            with patch.object(public.urllib.request, "urlopen", return_value=response(payload)):
                snapshot = public.fetch("https://example.test/api/health")
            self.assertEqual(snapshot[1], {})
            self.assertEqual(public.evaluate(*snapshot)["status"], "critical")

    def test_oversize_body_is_refused(self) -> None:
        with (
            patch.object(public.urllib.request, "urlopen", return_value=response(b"x" * 100_001)),
            self.assertRaises(ValueError),
        ):
            public.fetch("https://example.test/api/health")

    def test_cli_exit_codes_and_private_errors(self) -> None:
        arguments = ["--base-url", "https://example.test"]
        for status, code in ((200, 0), (503, 1)):
            output = io.StringIO()
            with (
                patch.object(
                    public,
                    "fetch",
                    return_value=(
                        status,
                        {"status": "ok", "schema": "compatible"},
                        "nginx",
                        1,
                    ),
                ),
                redirect_stdout(output),
            ):
                self.assertEqual(public.main(arguments), code)
            self.assertEqual(
                json.loads(output.getvalue())["status"], "ok" if code == 0 else "critical"
            )
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(public, "fetch", side_effect=URLError("private-token/private-url")),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            self.assertEqual(public.main(arguments), 2)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("private", errors.getvalue())

    def test_invalid_origin_fails_before_network(self) -> None:
        with patch.object(public, "fetch") as fetch, redirect_stderr(io.StringIO()):
            self.assertEqual(public.main(["--base-url", "http://example.test"]), 2)
        fetch.assert_not_called()


class OperationalTransportTests(unittest.TestCase):
    def test_bearer_request_is_bounded_and_reads_json(self) -> None:
        reply = response(b'{"schema":"compatible"}')
        with patch.object(operational.urllib.request, "urlopen", return_value=reply) as request:
            self.assertEqual(
                operational.fetch(
                    "https://example.test",
                    "/api/operations/readiness",
                    token="synthetic-token",
                ),
                {"schema": "compatible"},
            )
        sent = request.call_args.args[0]
        self.assertEqual(sent.full_url, "https://example.test/api/operations/readiness")
        self.assertEqual(sent.get_header("Authorization"), "Bearer synthetic-token")
        self.assertEqual(request.call_args.kwargs["timeout"], 5)
        reply.read.assert_called_once_with(1_000_001)

    def test_http_error_keeps_diagnostic_without_printing_payload(self) -> None:
        error = HTTPError(
            "https://example.test",
            503,
            "private",
            Message(),
            io.BytesIO(b'{"schema":"incompatible"}'),
        )
        self.addCleanup(error.close)
        with patch.object(operational.urllib.request, "urlopen", side_effect=error):
            self.assertEqual(
                operational.fetch("https://example.test", "/api/operations/readiness"),
                {"schema": "incompatible"},
            )

    def test_oversize_invalid_json_and_non_objects_are_refused(self) -> None:
        for payload in (b"x" * 1_000_001, b"private HTML", b"[]", b"null"):
            with (
                patch.object(operational.urllib.request, "urlopen", return_value=response(payload)),
                self.assertRaises(ValueError),
            ):
                operational.fetch("https://example.test", "/api/operations/readiness")

    def test_cli_missing_token_never_requests_network(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(operational, "fetch") as fetch,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(operational.main([]), 2)
        fetch.assert_not_called()

    def test_cli_network_failure_does_not_log_token_url_or_body(self) -> None:
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, {"OPERATIONS_TOKEN": "synthetic-token"}, clear=True),
            patch.object(operational, "fetch", side_effect=URLError("private-url synthetic-token")),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            self.assertEqual(operational.main([]), 2)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("private-url", errors.getvalue())
        self.assertNotIn("synthetic-token", errors.getvalue())
