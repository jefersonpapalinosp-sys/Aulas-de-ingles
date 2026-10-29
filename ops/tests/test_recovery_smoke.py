"""O smoke só aceita a fixture sintética e exige recusa de destino ocupado."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from ops import recovery_smoke as smoke
from ops.recovery_archive import RecoveryError


class RecoverySmokeCliTests(unittest.TestCase):
    def test_cli_reports_safe_failure_location_without_external_error_payload(self):
        for error in (RuntimeError("private-database-payload"), RecoveryError("Alvo recusado.")):
            output = io.StringIO()
            with patch.object(smoke, "main", side_effect=error), redirect_stderr(output):
                self.assertEqual(smoke.cli(), 1)
            self.assertIn("recovery_smoke.py:", output.getvalue())
            self.assertIn(type(error).__name__, output.getvalue())
            self.assertNotIn("private-database-payload", output.getvalue())
            if isinstance(error, RecoveryError):
                self.assertIn("Alvo recusado.", output.getvalue())

    def test_cli_success_does_not_emit_failure_diagnostic(self):
        output = io.StringIO()
        with patch.object(smoke, "main") as main, redirect_stderr(output):
            self.assertEqual(smoke.cli(), 0)
        main.assert_called_once_with()
        self.assertEqual(output.getvalue(), "")


class RecoverySmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = {"counts": {"users": 1, "speaking": 1}, "audio": ["synthetic"]}
        self.first, self.second, self.receipt = map(Path, ("first", "second", "receipt"))
        self.guards = self.replace("check_target")
        self.query = self.replace("query", return_value=self.snapshot)
        self.backup = self.replace("backup", side_effect=[self.first, self.second])
        self.verify = self.replace(
            "verify_bundle",
            return_value={
                "source": {"kind": "lab"},
                "snapshot": self.snapshot,
                "audio_files": {"key": {}},
            },
        )
        self.restore = self.replace(
            "restore",
            side_effect=[
                self.receipt,
                RecoveryError("PostgreSQL não está vazio"),
            ],
        )
        # Não alterar a umask do processo que roda os demais testes.
        self.replace("os.umask")

    def replace(self, name: str, **kwargs: object) -> MagicMock:
        replacement = patch(f"ops.recovery_smoke.{name}", **kwargs)
        mocked = replacement.start()
        self.addCleanup(replacement.stop)
        return mocked

    def test_success_requires_both_target_guards_and_checks_source_and_destination(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            smoke.main()
        self.assertEqual(self.guards.call_args_list, [call(smoke.LAB), call(smoke.RESTORE)])
        self.assertEqual(
            self.restore.call_args_list,
            [
                call(self.first, smoke.CONFIRM_TARGET),
                call(self.second, smoke.CONFIRM_TARGET),
            ],
        )
        self.assertEqual(
            self.query.call_args_list,
            [
                call(smoke.LAB, smoke.SNAPSHOT_SQL),
                call(smoke.LAB, smoke.SNAPSHOT_SQL),
                call(smoke.RESTORE, smoke.SNAPSHOT_SQL),
            ],
        )
        report = json.loads(output.getvalue())
        self.assertTrue(report["verified"] and report["nonempty_restore_blocked"])
        self.assertNotIn("audio", report)

    def test_real_or_unexpected_data_never_reaches_backup(self) -> None:
        self.query.return_value = {"counts": {"users": 2, "speaking": 1}}
        with self.assertRaises(RecoveryError):
            smoke.main()
        self.backup.assert_not_called()
        self.restore.assert_not_called()

    def test_wrong_source_or_missing_audio_never_reaches_restore(self) -> None:
        for manifest in (
            {"source": {"kind": "public"}, "snapshot": self.snapshot, "audio_files": {"k": {}}},
            {"source": {"kind": "lab"}, "snapshot": self.snapshot, "audio_files": {}},
        ):
            self.backup.side_effect = [self.first, self.second]
            self.verify.return_value = manifest
            with self.assertRaises(RecoveryError):
                smoke.main()
            self.restore.assert_not_called()

    def test_wrong_rejection_or_overwrite_cannot_be_reported_as_success(self) -> None:
        for result in (RecoveryError("falha não relacionada"), self.receipt):
            self.backup.side_effect = [self.first, self.second]
            self.restore.side_effect = [self.receipt, result]
            output = io.StringIO()
            with redirect_stdout(output), self.assertRaises(RecoveryError):
                smoke.main()
            self.assertEqual(output.getvalue(), "")

    def test_source_or_destination_drift_blocks_success_receipt(self) -> None:
        for changed in (1, 2):
            snapshots = [self.snapshot] * 3
            snapshots[changed] = {"counts": {"users": 99}}
            self.query.side_effect = snapshots
            self.backup.side_effect = [self.first, self.second]
            self.restore.side_effect = [self.receipt, RecoveryError("PostgreSQL não está vazio")]
            output = io.StringIO()
            with redirect_stdout(output), self.assertRaises(RecoveryError):
                smoke.main()
            self.assertEqual(output.getvalue(), "")
