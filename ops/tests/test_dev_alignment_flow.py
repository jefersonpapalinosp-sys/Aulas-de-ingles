"""Fluxo de provas/recibos em disco; banco, voz e migrations inteiramente simulados."""

import io
import json
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ops import concurrency_rollout, recovery
from ops import dev_alignment as alignment
from ops.recovery_archive import RecoveryError, file_info, write_json


class DevAlignmentFlowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.bundle = root / "bundle"
        self.bundle.mkdir()
        self.proofs = root / "proofs"
        self.proofs.mkdir()
        (self.proofs / "restore-receipts").mkdir()
        self.source = recovery.Target(
            "aulas-ingles", "db", "synthetic", "local", "db-volume", "voice-volume", None
        )
        self.snapshot = {"revision": [alignment.BASE], "counts": {"app_user": 1}, "audio": []}
        self.manifest = {
            "bundle_id": "bundle",
            "source": {
                "kind": "dev", "project": self.source.project, "database": self.source.database,
                "db_container_id": "synthetic-container", "voice_volume": self.source.voice_volume,
            },
            "snapshot": self.snapshot,
            "audio_files": {},
        }
        (self.bundle / "manifest.json").write_text(json.dumps(self.manifest))
        self.tables = {"app_user": {"count": 1, "sha256": "a" * 64}}
        self.migrated = set()
        self.post_migration_drift = False
        self.capture = self.proofs / "dev39-bundle-capture.json"
        self.rehearsal = self.proofs / "dev39-bundle-rehearse.json"
        self.applied = self.proofs / "dev39-bundle-apply.json"

        def query(target, sql):
            self.assertEqual(sql, recovery.SNAPSHOT_SQL)
            if target in self.migrated:
                return {**self.snapshot, "revision": [alignment.HEAD]}
            return self.snapshot

        def fingerprints(target):
            if self.post_migration_drift and target in self.migrated:
                return {"app_user": {"count": 1, "sha256": "b" * 64}}
            return self.tables

        self.patch(recovery, "BACKUPS", self.proofs)
        self.patch(recovery, "source_target", return_value=self.source)
        self.patch(recovery, "check_target", return_value={"Id": "synthetic-container"})
        self.patch(recovery, "quiet")
        self.patch(recovery, "lease", side_effect=lambda name: nullcontext())
        self.patch(recovery, "query", side_effect=query)
        self.patch(alignment, "verify_bundle", return_value=self.manifest)
        self.patch(alignment, "image_id", return_value="sha256:synthetic-image")
        self.patch(alignment, "fingerprints", side_effect=fingerprints)
        self.patch(alignment, "verify_voice")
        self.patch(alignment, "verify_initial_state")
        self.patch(
            concurrency_rollout, "audit", return_value=dict.fromkeys(concurrency_rollout.RULES, 0)
        )
        self.migrate = self.patch(
            alignment, "run_migration", side_effect=lambda target, image: self.migrated.add(target)
        )
        self.docker = self.patch(
            recovery, "docker", side_effect=AssertionError("Docker não permitido")
        )

    def patch(self, target, name, *args, **kwargs):
        patcher = patch.object(target, name, *args, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def run_action(self, action):
        output = io.StringIO()
        with redirect_stdout(output):
            alignment.run(action, self.bundle)
        return output.getvalue()

    def restore_receipt(self, **overrides):
        return {
            "verified": True, "bundle_id": "bundle", "target": recovery.CONFIRM_DEV_CHECK,
            "manifest": file_info(self.bundle / "manifest.json"), **overrides,
        }

    def prepare_rehearsal(self):
        self.run_action("capture")
        write_json(
            self.proofs / "restore-receipts/bundle.json", self.restore_receipt()
        )

    def test_capture_rehearse_apply_publishes_bound_receipts(self):
        self.prepare_rehearsal()
        self.migrate.assert_not_called()
        self.run_action("rehearse")
        receipt = concurrency_rollout.private_json(self.rehearsal)
        self.assertEqual(receipt["target"], recovery.CONFIRM_DEV_CHECK)
        self.assertEqual(receipt["tools_image"], "sha256:synthetic-image")
        self.assertEqual(receipt["manifest"], file_info(self.bundle / "manifest.json"))
        self.assertEqual((receipt["tables"], receipt["rows"], receipt["audio_count"]), (1, 1, 0))
        self.run_action("apply")
        applied = concurrency_rollout.private_json(self.applied)
        self.assertTrue(applied["verified"])
        self.assertEqual(applied["revision"], alignment.HEAD)
        self.assertEqual(applied["target"], "aulas-ingles/db")
        self.assertEqual(
            [call.args[0] for call in self.migrate.call_args_list],
            [recovery.DEV_CHECK, self.source],
        )
        for path in (self.capture, self.rehearsal, self.applied):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.docker.assert_not_called()

    def test_capture_rejects_source_drift_without_publishing_proof(self):
        with (
            patch.object(recovery, "query", return_value={**self.snapshot, "counts": {}}),
            self.assertRaisesRegex(RecoveryError, "Origem mudou"),
        ):
            self.run_action("capture")
        self.assertFalse(self.capture.exists())
        self.migrate.assert_not_called()

    def test_changed_capture_is_refused_before_migration(self):
        self.prepare_rehearsal()
        good = concurrency_rollout.private_json(self.capture)
        for field, value in (
            ("manifest", {}), ("tools_image", "different-image"), ("tables", []),
            ("audit", None), ("audit", {}),
            ("tables", {"app_user": {"count": True, "sha256": "a" * 64}}),
            ("tables", {"app_user": {"count": 1, "sha256": "b" * 64}}),
        ):
            self.capture.write_text(json.dumps({**good, field: value}))
            with self.subTest(field=field), self.assertRaises(RecoveryError):
                self.run_action("rehearse")
            self.migrate.assert_not_called()
            self.assertFalse(self.rehearsal.exists())

    def test_restore_must_bind_clone_and_current_bundle(self):
        self.prepare_rehearsal()
        path = self.proofs / "restore-receipts/bundle.json"
        for changes in (
            {"verified": False}, {"target": recovery.CONFIRM_STUDY_CHECK},
            {"bundle_id": "different-bundle"}, {"manifest": {}},
        ):
            path.write_text(json.dumps(self.restore_receipt(**changes)))
            with self.subTest(changes=changes), self.assertRaises(RecoveryError):
                self.run_action("rehearse")
            self.migrate.assert_not_called()

    def test_apply_requires_rehearsal_and_refuses_changed_binding(self):
        self.prepare_rehearsal()
        with self.assertRaises(RecoveryError):
            self.run_action("apply")
        self.migrate.assert_not_called()
        self.run_action("rehearse")
        good = concurrency_rollout.private_json(self.rehearsal)
        self.migrate.reset_mock()
        for field, value in (
            ("verified", False), ("tools_image", "different-image"), ("manifest", {}),
            ("revision", alignment.BASE), ("target", "aulas-ingles/db"),
        ):
            self.rehearsal.write_text(json.dumps({**good, field: value}))
            with self.subTest(field=field), self.assertRaises(RecoveryError):
                self.run_action("apply")
            self.migrate.assert_not_called()
            self.assertFalse(self.applied.exists())

    def test_historical_drift_after_migration_does_not_publish_success(self):
        self.prepare_rehearsal()
        self.post_migration_drift = True
        output = io.StringIO()
        with (
            redirect_stdout(output),
            self.assertRaisesRegex(RecoveryError, "históricos divergiram"),
        ):
            alignment.run("rehearse", self.bundle)
        self.migrate.assert_called_once()
        self.assertFalse(self.rehearsal.exists())
        self.assertEqual(output.getvalue(), "")
