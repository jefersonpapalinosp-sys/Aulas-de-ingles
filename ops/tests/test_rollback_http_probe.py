"""Contrato HTTP do smoke de rollback sem rede, relógio real ou dados de aluno."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from ops import rollback_http_probe as probe


class RollbackHttpProbeTests(unittest.TestCase):
    def test_get_uses_only_internal_api_and_bounded_timeout(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"status":"ok"}'
        with patch.object(probe.urllib.request, "urlopen", return_value=response) as request:
            self.assertEqual(probe.get("/api/health"), {"status": "ok"})
        request.assert_called_once_with("http://rollback-api:8000/api/health", timeout=3)
        response.__exit__.assert_called_once()

    def test_non_200_and_invalid_json_are_errors(self) -> None:
        for status, payload, error_type in (
            (503, b"private", RuntimeError),
            (200, b"{", ValueError),
        ):
            response = MagicMock()
            response.__enter__.return_value = response
            response.status, response.read.return_value = status, payload
            with (
                self.subTest(status=status),
                patch.object(probe.urllib.request, "urlopen", return_value=response),
                self.assertRaises(error_type),
            ):
                probe.get("/api/health")

    def test_retry_then_success_emits_only_aggregate_receipt(self) -> None:
        output = io.StringIO()
        with (
            patch.object(
                probe,
                "get",
                side_effect=[OSError("private"), {"status": "ok"}, [{"title": "private"}]],
            ),
            patch.object(probe.time, "monotonic", side_effect=[0, 1]),
            patch.object(probe.time, "sleep") as sleep,
            redirect_stdout(output),
        ):
            probe.main()
        sleep.assert_called_once_with(0.5)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "verified": True,
                "health": "ok",
                "catalog_nonempty": True,
            },
        )
        self.assertNotIn("private", output.getvalue())

    def test_bad_health_or_catalog_exhausts_deadline_without_success(self) -> None:
        for health, courses in (
            (None, [{}]),
            ([], [{}]),
            ("private", [{}]),
            ({"status": "degraded"}, [{}]),
            ({"status": "ok"}, []),
            ({"status": "ok"}, {"private": "not-a-list"}),
        ):
            output = io.StringIO()
            with (
                self.subTest(health=health, courses=courses),
                patch.object(probe, "get", side_effect=[health, courses]),
                patch.object(probe.time, "monotonic", side_effect=[0, 60]),
                patch.object(probe.time, "sleep") as sleep,
                redirect_stdout(output),
                self.assertRaises(SystemExit) as error,
            ):
                probe.main()
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(output.getvalue(), "")
            sleep.assert_not_called()
