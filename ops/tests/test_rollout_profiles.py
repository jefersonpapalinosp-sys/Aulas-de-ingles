"""INFRA-49: seleção de perfil não pode trocar clone, política ou recibo."""

import io
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ops import recovery, rollout
from ops.recovery_archive import RecoveryError, write_json


class RolloutProfilesTests(unittest.TestCase):
    def test_invalid_profile_and_policy_stop_before_backup_or_docker(self):
        for profile, preserve in (("prod", False), ("", False), ("study", True)):
            with (
                self.subTest(profile=profile),
                patch.object(rollout, "verify_bundle") as bundle,
                patch.object(recovery, "docker") as docker,
                self.assertRaises(RecoveryError),
            ):
                rollout.run("capture", Path("unused"), profile=profile, preserve_legacy=preserve)
            bundle.assert_not_called()
            docker.assert_not_called()

    def test_selected_clone_uses_only_its_disposable_database(self):
        for profile, target in (
            ("study", recovery.STUDY_CHECK), ("concurrency", recovery.CONCURRENCY_CHECK),
        ):
            def docker(*args, target=target, **kwargs):
                env_path = Path(args[args.index("--env-file") + 1])
                environment = env_path.read_text()
                self.assertIn(f"@{target.service}:5432/aulas_ingles_restore", environment)
                self.assertIn("ASSISTED_FEATURES_ENABLED=false", environment)
                self.assertNotIn("aulas_ingles_prod", environment)
                self.assertNotIn("--mount", args)
                self.assertNotIn("-p", args)
                self.assertEqual(args[args.index("--network") + 1], f"{target.project}_default")
                return b"ok"

            with (
                self.subTest(profile=profile),
                patch.object(recovery, "check_target") as check,
                patch.object(recovery, "quiet"),
                patch.object(recovery, "docker", side_effect=docker),
            ):
                self.assertEqual(rollout.clone_run("alembic", "current", profile=profile), b"ok")
                check.assert_called_once_with(target)

    def test_rehearsal_preserves_profile_revision_and_historical_receipt(self):
        for profile, target, revision, proof_name, receipt_name in (
            ("study", recovery.STUDY_CHECK, rollout.STUDY_HEAD,
             "rollout-synthetic.json", "rehearse-synthetic.json"),
            ("concurrency", recovery.CONCURRENCY_CHECK, rollout.CONCURRENCY_HEAD,
             "sprint38-capture-synthetic.json", "sprint38-rehearse-synthetic.json"),
        ):
            with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                root = Path(directory)
                info = {"size": 1, "sha256": "a" * 64}
                snapshot = {"revision": [rollout.CONCURRENCY_BASE]}
                manifest = {
                    "bundle_id": "synthetic", "source": {"kind": "prod", "database": "source"},
                    "snapshot": snapshot, "audio_files": {},
                }
                proof = {
                    "manifest": info, "tables": {}, "audit": dict.fromkeys(rollout.RULES, 0),
                    "preserve_legacy": False,
                }
                write_json(root / proof_name, proof)
                stack.enter_context(patch.object(recovery, "BACKUPS", root))
                stack.enter_context(patch.object(rollout, "verify_bundle", return_value=manifest))
                stack.enter_context(patch.object(rollout, "file_info", return_value=info))
                source = stack.enter_context(patch.object(recovery, "source_target"))
                source.return_value.database = "source"
                stack.enter_context(patch.object(recovery, "check_target"))
                stack.enter_context(patch.object(recovery, "quiet"))
                stack.enter_context(patch.object(rollout, "validate_restore"))
                stack.enter_context(patch.object(rollout, "audit", return_value=proof["audit"]))
                stack.enter_context(patch.object(rollout, "verify_new_state"))
                stack.enter_context(patch.object(rollout, "fingerprints", return_value={}))
                stack.enter_context(patch.object(recovery, "voice"))
                stack.enter_context(patch.object(rollout, "audio_inventory", return_value={}))
                query = stack.enter_context(patch.object(
                    recovery, "query", side_effect=[snapshot, {"revision": [revision]}]
                ))
                clone = stack.enter_context(patch.object(rollout, "clone_run"))
                stack.enter_context(redirect_stdout(io.StringIO()))

                rollout.run("rehearse", root, profile=profile)

                receipt = rollout.private_json(root / receipt_name)
                self.assertIs(receipt["verified"], True)
                self.assertEqual(receipt["revision"], revision)
                self.assertEqual(receipt["manifest"], info)
                self.assertTrue(all(call.args[0] == target for call in query.call_args_list))
                self.assertTrue(all(call.kwargs == {"profile": profile}
                                    for call in clone.call_args_list))
                self.assertEqual(clone.call_args_list[0].args, ("alembic", "upgrade", revision))
                if profile == "concurrency":
                    self.assertEqual(clone.call_count, 2)
                    self.assertEqual(clone.call_args_list[0], clone.call_args_list[1])
                else:
                    self.assertEqual(clone.call_count, 3)
                    self.assertEqual(clone.call_args_list[1].args[-1], "writing-rubrics")
