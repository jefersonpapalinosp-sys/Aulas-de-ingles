import contextlib
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from ops import backup_policy, backup_watch, observability_check, public_restore, recovery
from ops.diagnostics import diagnostic
from ops.recovery_archive import RecoveryError, file_info
from ops.recovery_prune import apply_prune, plan_prune
from ops.tests.test_observability_check import metrics, readiness
from ops.tests.test_public_backup import SNAPSHOT
from ops.tests.test_recovery_prune import at, make_bundle


class BackupPolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_hold_survives_same_day_pruning_and_late_hold_blocks_old_plan(self):
        before = make_bundle(self.root, at(11, 5, 8))
        make_bundle(self.root, at(11, 5, 9))
        plan = plan_prune(self.root)
        self.assertIn(before.name, plan.targets())
        backup_policy.hold(self.root, before.name)
        with self.assertRaises(RecoveryError):
            apply_prune(plan)
        self.assertNotIn(before.name, plan_prune(self.root).targets())
        backup_policy.hold(self.root, before.name, release=True)
        self.assertIn(before.name, plan_prune(self.root).targets())

    def test_encrypted_policy_keeps_hold_newest_and_unknown_files(self):
        old = make_bundle(self.root, at(11, 5, 8)).name
        new = make_bundle(self.root, at(11, 5, 9)).name
        for name in (old, new):
            path = self.root / f"{name}.tar.age"
            path.write_bytes(b"age-encrypted-synthetic")
            backup_policy.record_copy(path, file_info(path))
        (self.root / "foreign.tar.age").write_bytes(b"preserve")
        backup_policy.hold(self.root, old)
        self.assertEqual(backup_policy.prune_encrypted(self.root)["remove"], {})
        backup_policy.hold(self.root, old, release=True)
        self.assertIn(old, backup_policy.prune_encrypted(self.root)["remove"])
        self.assertTrue((self.root / f"{old}.tar.age").exists())
        backup_policy.prune_encrypted(self.root, apply=True)
        self.assertFalse((self.root / f"{old}.tar.age").exists())
        self.assertTrue((self.root / f"{new}.tar.age").exists())
        self.assertTrue((self.root / "foreign.tar.age").exists())

    def test_status_missing_stale_future_failed_and_success(self):
        path = self.root / "status.json"
        now = datetime.now(UTC)
        self.assertEqual(backup_watch.freshness(path, now), (False, None))
        for hours, success, expected in (
            (1, True, True),
            (24, True, True),
            (25, True, False),
            (-1, True, False),
            (1, False, False),
        ):
            backup_watch.save_status(
                path,
                {
                    "last_success_at": (now - timedelta(hours=hours)).isoformat(),
                    "last_attempt_ok": success,
                },
            )
            self.assertEqual(backup_watch.freshness(path, now)[0], expected)

    def test_failed_capture_does_not_refresh_last_success_and_gate_fails(self):
        path = self.root / "status.json"
        old = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        backup_watch.save_status(path, {"last_success_at": old, "last_attempt_ok": True})
        external = self.root / "external"
        external.mkdir()
        with patch.object(backup_watch.public_backup, "main", return_value=1):
            code = backup_watch.run(
                path,
                host="local",
                recipient=self.root / "public-key",
                encrypted=self.root / "encrypted",
                external=external,
            )
        self.assertEqual(code, 1)
        self.assertEqual(backup_watch.read_status(path)["last_success_at"], old)
        with (
            patch.dict("os.environ", {"OPERATIONS_TOKEN": "synthetic"}),
            patch.object(observability_check, "fetch", side_effect=[readiness(), metrics()]),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(observability_check.main(["--backup-status-file", str(path)]), 1)
        report = json.loads(output.getvalue())
        check = next(c for c in report["checks"] if c["name"] == "last_backup_age_hours")
        self.assertEqual(check["state"], "critical")

    def test_success_status_requires_completed_external_capture(self):
        path = self.root / "status.json"
        external = self.root / "external"
        external.mkdir()
        with patch.object(backup_watch.public_backup, "main", return_value=0) as capture:
            self.assertEqual(
                backup_watch.run(
                    path,
                    host="local",
                    recipient=self.root / "key",
                    encrypted=self.root / "enc",
                    external=external,
                ),
                0,
            )
        self.assertTrue(backup_watch.freshness(path)[0])
        self.assertIn("--copy-to", capture.call_args.args[0])

    def test_lease_break_requires_full_id_age_and_explicit_owner_confirmation(self):
        identity = "a" * 64
        info = {
            "Id": identity,
            "Config": {"Labels": {"org.aulas.purpose": "recovery-lock"}},
            "State": {"Running": False},
            "Created": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        }
        with (
            patch.object(recovery, "local_daemon"),
            patch.object(recovery, "docker", return_value=json.dumps([info]).encode()) as docker,
        ):
            with self.assertRaises(RecoveryError):
                recovery.break_lease("restore", identity, False)
            docker.assert_not_called()
            recovery.break_lease("restore", identity, True)
            self.assertEqual(docker.call_args.args, ("rm", identity))
            info["Created"] = datetime.now(UTC).isoformat()
            docker.return_value = json.dumps([info]).encode()
            docker.reset_mock()
            with self.assertRaises(RecoveryError):
                recovery.break_lease("restore", identity, True)
            self.assertEqual(docker.call_count, 1)

    def test_diagnostic_never_prints_error_payload(self):
        with contextlib.redirect_stderr(io.StringIO()) as output:
            diagnostic("backup_test", PermissionError("password and private learner text"))
        report = json.loads(output.getvalue())
        self.assertEqual(report["category"], "permission")
        self.assertNotIn("password", output.getvalue())

    def test_restore_rejects_existing_project_and_bad_package_before_remote_calls(self):
        with self.assertRaises(RecoveryError):
            public_restore.Destination("local", "papalino_aulas-ingles")
        destination = public_restore.Destination("local", "aulas-dr-test")
        with patch.object(destination, "call") as call:
            with self.assertRaises(RecoveryError):
                public_restore.restore(
                    self.root / "missing", destination, "local/aulas-dr-test", self.root
                )
            call.assert_not_called()

    def test_restore_partial_failure_preserves_target_and_never_announces_receipt(self):
        destination = public_restore.Destination("local", "aulas-dr-test")
        destination.image = "sha256:" + "b" * 64
        with (
            patch.object(
                public_restore,
                "verify_bundle",
                return_value={
                    "source": {"kind": "public"},
                    "snapshot": SNAPSHOT,
                    "application": {
                        "deployed_containers": [{"service": "api", "image_id": destination.image}]
                    },
                },
            ),
            patch.object(destination, "check"),
            patch.object(destination, "sql", return_value=1),
            patch.object(destination, "call", return_value=("a" * 64).encode()) as call,
            self.assertRaises(RecoveryError),
        ):
            public_restore.restore(
                self.root, destination, "local/aulas-dr-test", self.root / "receipts"
            )
        self.assertFalse((self.root / "receipts").exists())
        self.assertFalse(any("pg_restore" in c.args[0] for c in call.call_args_list))
        self.assertFalse(any("volume rm" in c.args[0] for c in call.call_args_list))


if __name__ == "__main__":
    unittest.main()
