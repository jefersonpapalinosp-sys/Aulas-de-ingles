"""Guardas do laboratório INFRA-48: nenhum destino arbitrário ou sobrescrita."""

import json
import unittest
from unittest.mock import patch

from ops import dialogue_recovery as lab
from ops import recovery as r
from ops.recovery_archive import RecoveryError


class DialogueRecoveryTests(unittest.TestCase):
    def test_fingerprints_validate_database_response_without_logging_content(self):
        for value in (None, [], {"count": True, "digest": "private"},
                      {"count": -1, "digest": "private"}, {"count": 1, "digest": None}):
            with (
                self.subTest(value=value),
                patch.object(r, "query", return_value=value),
                self.assertRaises(RecoveryError) as error,
            ):
                lab.fingerprints(r.DIALOGUE_LAB)
            self.assertNotIn("private", str(error.exception))
        with patch.object(r, "query", return_value={"count": 2, "digest": "a" * 32}):
            result = lab.fingerprints(r.DIALOGUE_LAB)
        self.assertEqual(set(result), set(lab.TABLES))
        self.assertTrue(all(item == {"count": 2, "digest": "a" * 32} for item in result.values()))

    def test_application_read_rejects_nonobject_response(self):
        with patch.object(r, "docker", return_value=b'[]'), self.assertRaises(RecoveryError):
            lab.application_read()

    def test_source_and_destination_are_explicit_and_separate(self):
        self.assertEqual(r.source_target("dialogue-lab"), r.DIALOGUE_LAB)
        self.assertEqual(r.DIALOGUE_DESTINATIONS[r.CONFIRM_DIALOGUE], r.DIALOGUE_RESTORE)
        self.assertNotIn(r.CONFIRM_DIALOGUE, r.DESTINATIONS)
        self.assertNotEqual(r.DIALOGUE_LAB.project, r.LAB.project)
        with self.assertRaises(RecoveryError):
            r.source_target("untrusted-project")

    def test_prepare_rejects_existing_source_before_running_fixture(self):
        with (
            patch.object(r, "quiet"),
            patch.object(r, "query", return_value=1),
            patch.object(r, "docker") as docker,
        ):
            with self.assertRaises(RecoveryError):
                r._prepare_empty_lab(r.DIALOGUE_LAB)
            docker.assert_not_called()

    def test_prepare_rejects_destination_or_study_before_access(self):
        with patch.object(r, "quiet") as quiet:
            with self.assertRaises(RecoveryError):
                r._prepare_empty_lab(r.DIALOGUE_RESTORE)
            quiet.assert_not_called()

    def test_check_rejects_nonempty_destination_before_backup(self):
        with (
            patch.object(r, "check_target"),
            patch.object(r, "query", return_value=1),
            patch.object(r, "backup") as backup,
        ):
            with self.assertRaises(RecoveryError):
                lab.check()
            backup.assert_not_called()

    def test_check_rejects_nonsynthetic_source_before_backup(self):
        with (
            patch.object(r, "check_target"),
            patch.object(r, "query", side_effect=[0, False]),
            patch.object(r, "backup") as backup,
        ):
            with self.assertRaises(RecoveryError):
                lab.check()
            backup.assert_not_called()

    def test_external_network_is_rejected(self):
        network = {
            "Internal": False,
            "Driver": "bridge",
            "Labels": {"com.docker.compose.project": r.DIALOGUE_PROJECT},
        }
        with (
            patch.object(r, "local_daemon"),
            patch.object(
                r,
                "docker",
                side_effect=[
                    b"",
                    f"{r.DIALOGUE_PROJECT}_default".encode(),
                    json.dumps([network]).encode(),
                ],
            ),
            self.assertRaises(RecoveryError),
        ):
            lab.resources()

    def test_application_mounts_are_read_only_and_down_keeps_volumes(self):
        with patch.object(r, "docker", return_value=b'{"verified":true}') as docker:
            self.assertTrue(lab.application_read()["verified"])
            args = docker.call_args.args
            mounts = [args[i + 1] for i, arg in enumerate(args) if arg == "--mount"]
            self.assertTrue(all(m.endswith(",readonly") for m in mounts))
            self.assertIn("--read-only", args)
            self.assertIn(f"{r.DIALOGUE_PROJECT}_default", args)
        with patch.object(lab, "resources"), patch.object(r, "docker") as docker:
            lab.main(["down"])
            self.assertEqual(docker.call_args.args[-1], "down")
            self.assertNotIn("-v", docker.call_args.args)
