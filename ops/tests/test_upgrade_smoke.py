"""Upgrade só em clone: integridade, prazo, rollback e recibos sem Docker real."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import call, patch

from ops import upgrade_smoke as smoke
from ops.recovery_archive import RecoveryError


class UpgradeProcessTests(unittest.TestCase):
    def test_readonly_probe_uses_only_restore_volume_and_isolated_network(self):
        args = smoke.app_args("/tools/check.py", voice_read_only=True)
        self.assertIn(f"{smoke.UPGRADE_PROJECT}_default", args)
        self.assertIn(
            f"type=volume,src={smoke.UPGRADE_RESTORE.voice_volume},dst=/app/data/speaking,readonly",
            args,
        )
        self.assertIn("--read-only", args)
        self.assertIn("10001:10001", args)
        self.assertNotIn("-p", args)
        self.assertEqual(args[-1], "/tools/check.py")
        self.assertNotIn("--mount", smoke.app_args("alembic", "check"))

    def test_migration_samples_peak_waiters_and_removes_container(self):
        with (
            patch.object(
                smoke, "docker", side_effect=[b"container", b"true", b"false", b"0", b""]
            ) as docker,
            patch.object(smoke, "query", side_effect=[{"waiting": 3}, {"waiting": 0}]),
            patch.object(smoke.time, "monotonic", side_effect=[0, 1, 2]),
            patch.object(smoke.time, "sleep"),
        ):
            self.assertEqual(smoke.migrate_with_lock_sampling(), (2, 3))
        self.assertEqual(docker.call_args, call("rm", "-f", "container"))
        self.assertIn(f"{smoke.UPGRADE_PROJECT}_default", docker.call_args_list[0].args)

    def test_migration_failure_or_timeout_removes_only_ephemeral_container(self):
        for timeout in (False, True):
            replies = (
                [b"container", b"true", b""] if timeout else [b"container", b"false", b"1", b""]
            )
            with (
                self.subTest(timeout=timeout),
                patch.object(smoke, "docker", side_effect=replies) as docker,
                patch.object(smoke, "query", return_value={"waiting": 0}),
                patch.object(smoke.time, "monotonic", side_effect=[0, 181]),
                self.assertRaises(RecoveryError),
            ):
                smoke.migrate_with_lock_sampling()
            self.assertEqual(docker.call_args, call("rm", "-f", "container"))
            self.assertFalse(any("volume" in c.args for c in docker.call_args_list))

    def test_rollback_probe_uses_previous_image_and_cleans_up_on_rejection(self):
        for verified in (True, False):
            probe = {"verified": verified, "health": {"status": "ok"}, "catalog_nonempty": True}
            replies = [b"container", json.dumps(probe).encode()]
            if verified:
                replies.append(b'[{"Id":"sha256:synthetic"}]')
            replies.append(b"")
            with patch.object(smoke, "docker", side_effect=replies) as docker:
                if verified:
                    result = smoke.rollback_application_probe()
                    self.assertEqual(result["revision"], smoke.ROLLBACK_REVISION)
                    self.assertEqual(result["image_id"], "sha256:synthetic")
                else:
                    with self.assertRaises(RecoveryError):
                        smoke.rollback_application_probe()
            self.assertIn(smoke.ROLLBACK_IMAGE, docker.call_args_list[0].args)
            self.assertEqual(docker.call_args, call("rm", "-f", "container"))

    def test_post_restore_rejects_elevated_role_and_unvalidated_constraints(self):
        role = dict(
            role="aulas_restore",
            database_owner="aulas_restore",
            can_connect=True,
            superuser=False,
            createdb=False,
            createrole=False,
            bypassrls=False,
            replication=False,
        )
        references = {"foreign_keys": 5, "unvalidated": 0}
        with patch.object(smoke, "query", side_effect=[role, references]):
            self.assertEqual(smoke.post_restore_invariants()["role"], role)
        for field, value in (
            ("role", "other"),
            ("database_owner", "other"),
            ("can_connect", False),
            *(
                (key, True)
                for key in ("superuser", "createdb", "createrole", "bypassrls", "replication")
            ),
        ):
            with (
                self.subTest(field=field),
                patch.object(smoke, "query", return_value={**role, field: value}) as query,
                self.assertRaises(RecoveryError),
            ):
                smoke.post_restore_invariants()
            self.assertEqual(query.call_count, 1)
        for invalid in (
            {"foreign_keys": 0, "unvalidated": 0},
            {"foreign_keys": 5, "unvalidated": 1},
        ):
            with (
                patch.object(smoke, "query", side_effect=[role, invalid]),
                self.assertRaises(RecoveryError),
            ):
                smoke.post_restore_invariants()


class UpgradeFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = {
            "revision": [smoke.UPGRADE_FROM],
            "counts": dict(smoke.PERSONAL_COUNTS),
            "audio": ["synthetic"],
        }
        self.before = deepcopy(self.source)
        self.after = {**deepcopy(self.source), "revision": ["current-head"]}
        self.bundle = self.directory / "bundle"
        self.bundle.mkdir()
        (self.bundle / "manifest.json").write_text("{}")
        self.restore_receipt = self.directory / "restore.json"
        self.restore_receipt.write_text("{}")
        self.replace("BACKUPS", new=self.directory)
        self.replace("os.umask")
        self.guards = self.replace("check_target")
        self.query = self.replace(
            "query",
            side_effect=[self.source, self.before, {"waiting": 0}, self.after, {"waiting": 0}],
        )
        self.backup = self.replace("backup", return_value=self.bundle)
        self.verify = self.replace(
            "verify_bundle",
            return_value={"snapshot": deepcopy(self.source), "bundle_id": "synthetic"},
        )
        self.restore = self.replace("restore", return_value=self.restore_receipt)
        self.replace("voice")
        self.inventory = self.replace(
            "audio_inventory", return_value={"audio": {"sha256": "synthetic"}}
        )
        self.replace("quiet")
        self.migrate = self.replace("migrate_with_lock_sampling", return_value=(1.5, 2))
        self.docker = self.replace("docker", return_value=b'{"verified":true}')
        self.replace("post_restore_invariants", return_value={"verified": True})
        self.replace("rollback_application_probe", return_value={"verified": True})
        self.replace("required_schema_heads", return_value=("current-head",))
        self.output = self.enterContext(redirect_stdout(io.StringIO()))

    def replace(self, name, **kwargs):
        return self.enterContext(patch(f"ops.upgrade_smoke.{name}", **kwargs))

    def assert_no_receipt(self):
        self.assertFalse((self.directory / "upgrade-receipts").exists())
        self.assertEqual(self.output.getvalue(), "")

    def test_success_writes_private_receipt_bound_to_backup_and_restore(self):
        smoke.main()
        self.assertEqual(
            self.guards.call_args_list, [call(smoke.UPGRADE_LAB), call(smoke.UPGRADE_RESTORE)]
        )
        self.restore.assert_called_once_with(self.bundle, smoke.CONFIRM_UPGRADE42)
        report = json.loads(self.output.getvalue())
        path = Path(report["receipt"])
        receipt = json.loads(path.read_text())
        self.assertTrue(receipt["verified"])
        self.assertFalse(receipt["rpo_cadence_verified"])
        self.assertEqual(receipt["maximum_waiting_locks_sampled"], 2)
        self.assertEqual(receipt["to_revision"], ["current-head"])
        self.assertEqual(receipt["counts"], smoke.PERSONAL_COUNTS)
        self.assertIn("sha256", receipt["manifest"])
        self.assertIn("sha256", receipt["restore_receipt"])
        self.assertEqual(path.stat().st_mode & 0o077, 0)

    def test_guard_failure_never_queries_or_backs_up(self):
        self.guards.side_effect = RecoveryError("unsafe target")
        with self.assertRaises(RecoveryError):
            smoke.main()
        self.query.assert_not_called()
        self.backup.assert_not_called()
        self.assert_no_receipt()

    def test_wrong_source_revision_or_incomplete_fixture_stops_before_backup(self):
        for invalid in ({**self.source, "revision": ["wrong"]}, {**self.source, "counts": {}}):
            self.query.side_effect = [invalid]
            with self.assertRaises(RecoveryError):
                smoke.main()
        self.backup.assert_not_called()
        self.assert_no_receipt()

    def test_backup_drift_stops_before_restore(self):
        self.verify.return_value["snapshot"]["counts"]["users"] = 9
        with self.assertRaises(RecoveryError):
            smoke.main()
        self.restore.assert_not_called()
        self.assert_no_receipt()

    def test_migration_failure_never_writes_verified_receipt(self):
        self.migrate.side_effect = RecoveryError("migration failure")
        with self.assertRaises(RecoveryError):
            smoke.main()
        self.docker.assert_not_called()
        self.assert_no_receipt()

    def test_failed_application_probe_cannot_report_success(self):
        self.docker.return_value = b'{"verified":false}'
        with self.assertRaises(RecoveryError):
            smoke.main()
        self.assert_no_receipt()

    def test_schema_counts_references_checksums_and_locks_must_survive_upgrade(self):
        for change in ("revision", "counts", "audio", "checksum", "lock"):
            after = deepcopy(self.after)
            if change in after:
                after[change] = [] if change != "counts" else {}
            self.query.side_effect = [
                self.source,
                self.before,
                {"waiting": 0},
                after,
                {"waiting": int(change == "lock")},
            ]
            self.inventory.side_effect = [
                {"voice": "same"},
                {"voice": "different" if change == "checksum" else "same"},
            ]
            with self.subTest(change=change), self.assertRaises(RecoveryError):
                smoke.main()
            self.assert_no_receipt()

    def test_unsafe_receipt_directory_is_refused(self):
        destination = self.directory / "other"
        destination.mkdir()
        (self.directory / "upgrade-receipts").symlink_to(destination)
        with self.assertRaises(RecoveryError):
            smoke.main()
        self.assertEqual(list(destination.iterdir()), [])
        self.assertEqual(self.output.getvalue(), "")
