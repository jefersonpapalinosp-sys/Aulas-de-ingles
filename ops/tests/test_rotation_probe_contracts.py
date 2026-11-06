"""Recibos e limites de rotação; não abre conexões nem usa credenciais reais."""

import unittest

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
