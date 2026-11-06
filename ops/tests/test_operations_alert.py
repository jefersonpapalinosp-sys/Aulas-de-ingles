import contextlib
import io
import unittest
from unittest.mock import patch

from ops import operations_alert


class OperationsAlertTests(unittest.TestCase):
    def run_alert(self, status, *, report="", diagnostic=""):
        def gate(argv):
            self.assertEqual(argv, ["--base-url", "https://example.test"])
            print(report)
            if diagnostic:
                import sys

                print(diagnostic, file=sys.stderr)
            return status

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(operations_alert.observability_check, "main", side_effect=gate),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = operations_alert.main(["--base-url", "https://example.test"])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_healthy_gate_is_silent_for_cron(self):
        result, stdout, stderr = self.run_alert(0, report='{"status":"ok"}')
        self.assertEqual((result, stdout, stderr), (0, "", ""))

    def test_unhealthy_gate_preserves_exit_code_and_report(self):
        result, stdout, stderr = self.run_alert(1, report='{"status":"critical"}')
        self.assertEqual(result, 1)
        self.assertEqual(stdout, "")
        self.assertIn("ALERTA operacional", stderr)
        self.assertIn('"critical"', stderr)

    def test_missing_token_or_network_failure_is_not_success(self):
        result, _, stderr = self.run_alert(2, diagnostic="OPERATIONS_TOKEN ausente.")
        self.assertEqual(result, 2)
        self.assertIn("OPERATIONS_TOKEN ausente.", stderr)

    def test_unexpected_exception_never_leaks_its_message(self):
        stderr = io.StringIO()
        with (
            patch.object(
                operations_alert.observability_check,
                "main",
                side_effect=RuntimeError("sensitive-token-and-url"),
            ),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(operations_alert.main([]), 2)
        self.assertNotIn("sensitive-token-and-url", stderr.getvalue())
        self.assertIn("falha interna", stderr.getvalue())
