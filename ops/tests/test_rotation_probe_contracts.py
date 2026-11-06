"""Recibos e limites de rotação; não abre conexões nem usa credenciais reais."""

import subprocess
import unittest
from unittest.mock import Mock, patch

from ops import rotation_probe
from ops.recovery_archive import RecoveryError


class RotationProbeContracts(unittest.TestCase):
    def test_receipt_requires_all_proofs_with_exact_types_and_bounded_timings(self):
        valid = {**rotation_probe.EXPECTED, **dict.fromkeys(rotation_probe.TIMINGS, 10)}
        self.assertEqual(rotation_probe.validate_report(valid), valid)
        for field in valid:
            changed = dict(valid)
            changed.pop(field)
            with self.subTest(missing=field), self.assertRaises(RecoveryError):
                rotation_probe.validate_report(changed)
        for key, value in (
            ("verified", 1), ("database_roles", True), ("jwt_login_status", 401),
            ("runtime_stale_startup_rejected", 1), ("runtime_stale_startup_rejected", False),
            ("total_ms", -1), ("total_ms", 300001), ("secret", "must-not-be-accepted"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(RecoveryError):
                rotation_probe.validate_report({**valid, key: value})

    def test_connection_url_cannot_escape_fixed_lab(self):
        for role, password in (
            ("production", "x" * 24), ("aulas_runtime", "short"),
            ("aulas_runtime", "x" * 24 + "@remote"),
        ):
            with self.subTest(role=role), self.assertRaises(RecoveryError):
                rotation_probe.url(role, password)
        self.assertTrue(rotation_probe.url("aulas_runtime", "x" * 24).endswith(
            "@db:5432/aulas_rotation_lab"
        ))

    def test_stale_runtime_requires_natural_startup_failure(self):
        process = Mock()
        process.wait.return_value = 3
        process.poll.return_value = 3
        with patch.object(rotation_probe, "api_process", return_value=process):
            self.assertIs(rotation_probe.stale_startup_rejected({}), True)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()
        for code in (0, 1, -15, -9):
            with self.subTest(exit_code=code):
                process.wait.return_value = code
                process.poll.return_value = code
                with (
                    patch.object(rotation_probe, "api_process", return_value=process),
                    self.assertRaises(RecoveryError),
                ):
                    rotation_probe.stale_startup_rejected({})

    def test_stale_runtime_timeout_cleans_process_without_proving_rejection(self):
        for slow_shutdown in (False, True):
            process = Mock()
            timeout = subprocess.TimeoutExpired("synthetic-api", 10)
            process.wait.side_effect = [timeout, timeout, -9] if slow_shutdown else [timeout, -15]
            process.poll.return_value = None
            with (
                self.subTest(slow_shutdown=slow_shutdown),
                patch.object(rotation_probe, "api_process", return_value=process),
                self.assertRaises(subprocess.TimeoutExpired),
            ):
                rotation_probe.stale_startup_rejected({})
            process.terminate.assert_called_once()
            self.assertEqual(process.kill.call_count, int(slow_shutdown))
