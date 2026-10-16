import unittest
from pathlib import Path
from unittest.mock import patch

from ops import dev_alignment, recovery
from ops.recovery_archive import RecoveryError


class DevAlignmentTests(unittest.TestCase):
    def test_refuses_other_sources_and_revisions_before_docker(self):
        for kind, project, revision in (
            ("prod", "aulas-ingles-prod", dev_alignment.BASE),
            ("lab", recovery.PROJECT, dev_alignment.BASE),
            ("dev", "aulas-ingles-prod", dev_alignment.BASE),
            ("dev", "aulas-ingles", dev_alignment.HEAD),
        ):
            with (
                patch.object(
                    dev_alignment,
                    "verify_bundle",
                    return_value={
                        "source": {"kind": kind, "project": project},
                        "snapshot": {"revision": [revision]},
                    },
                ),
                patch.object(recovery, "source_target") as target,
                self.assertRaises(RecoveryError),
            ):
                dev_alignment.run("apply", Path("unused"))
            target.assert_not_called()

    def test_restore_target_is_new_and_never_development(self):
        self.assertEqual(recovery.DESTINATIONS[recovery.CONFIRM_DEV_CHECK], recovery.DEV_CHECK)
        self.assertTrue(all(t.project == recovery.PROJECT for t in recovery.DESTINATIONS.values()))
        self.assertNotIn("aulas-ingles/db", recovery.DESTINATIONS)
        self.assertEqual(
            len(recovery.DESTINATIONS),
            len({t.db_volume for t in recovery.DESTINATIONS.values()}),
        )

    def test_rehearsal_receipt_binds_image_backup_target_and_revision(self):
        good = {
            "verified": True,
            "revision": dev_alignment.HEAD,
            "target": recovery.CONFIRM_DEV_CHECK,
            "manifest": {"sha256": "abc"},
            "tools_image": "sha256:image",
        }
        dev_alignment.validate_receipt(
            good, manifest_hash=good["manifest"], tools_image=good["tools_image"]
        )
        for field, value in (
            ("verified", False),
            ("revision", dev_alignment.BASE),
            ("target", recovery.CONFIRM_CONCURRENCY_CHECK),
            ("manifest", {}),
            ("tools_image", "other"),
        ):
            with self.subTest(field=field), self.assertRaises(RecoveryError):
                dev_alignment.validate_receipt(
                    {**good, field: value},
                    manifest_hash=good["manifest"],
                    tools_image=good["tools_image"],
                )

    def test_migrator_refuses_production_before_any_command(self):
        prod = recovery.Target("aulas-ingles-prod", "db", "study", "owner", "db", "voice", None)
        with (
            patch.object(recovery, "source_target", return_value="dev"),
            patch.object(recovery, "check_target") as check,
            self.assertRaises(RecoveryError),
        ):
            dev_alignment.run_migration(prod, "sha256:image")
        check.assert_not_called()

    def test_clone_migrator_cannot_mount_origin_or_run_seed(self):
        with (
            patch.object(recovery, "check_target"),
            patch.object(recovery, "quiet"),
            patch.object(recovery, "docker") as docker,
        ):
            dev_alignment.run_migration(recovery.DEV_CHECK, "sha256:immutable")
        self.assertEqual(docker.call_count, 3)
        for call in docker.call_args_list:
            args = call.args
            self.assertIn("aulas-ingles-recovery_default", args)
            self.assertIn("sha256:immutable", args)
            self.assertIn("--read-only", args)
            self.assertNotIn("--mount", args)
            self.assertNotIn("seed", args)
            self.assertNotIn("aulas-ingles_default", args)
            self.assertNotIn("aulas-ingles-prod_default", args)

    def test_only_added_columns_are_excluded_from_preservation(self):
        self.assertNotIn("writing_prompt", dev_alignment.NEW_COLUMNS)
        self.assertNotIn("position_seconds", dev_alignment.NEW_COLUMNS["media_progress"])
        self.assertNotIn("total_seconds", dev_alignment.NEW_COLUMNS["study_session_progress"])
        with patch.object(dev_alignment.study_rollout, "fingerprints") as fingerprint:
            dev_alignment.fingerprints(recovery.DEV_CHECK)
        self.assertEqual(fingerprint.call_args.kwargs["excluded_tables"], dev_alignment.NEW_TABLES)

    def test_new_state_rejects_fabricated_events_or_changed_legacy(self):
        with patch.object(recovery, "query", return_value=0):
            dev_alignment.verify_initial_state(recovery.DEV_CHECK)
        with (
            patch.object(recovery, "query", return_value=1),
            self.assertRaises(RecoveryError),
        ):
            dev_alignment.verify_initial_state(recovery.DEV_CHECK)

    def test_running_development_blocks_backup(self):
        target = recovery.Target("aulas-ingles", "db", "dev", "app", "db", "voice", None)
        with (
            patch.object(recovery, "container", return_value={"State": {"Running": True}}),
            patch.object(recovery, "docker") as command,
            self.assertRaises(RecoveryError),
        ):
            recovery.quiet(target)
        command.assert_not_called()

    def test_dev_source_does_not_look_up_production(self):
        def container(project, service):
            self.assertEqual(project, "aulas-ingles")
            env = ["POSTGRES_DB=dev", "POSTGRES_USER=local"] if service == "db" else ["APP_ENV=dev"]
            return {"Config": {"Env": env}}

        with patch.object(recovery, "container", side_effect=container):
            target = recovery.source_target("dev")
        self.assertEqual(target.db_volume, "aulas-ingles-pgdata")
        self.assertEqual(target.voice_volume, "aulas-ingles-speaking-data")

    def test_dev_source_rejects_prod_config_and_role_overlays(self):
        for env in (["APP_ENV=prod"], ["APP_ENV=dev", "DATABASE_PURPOSE=runtime"]):
            with (
                patch.object(
                    recovery,
                    "container",
                    side_effect=[
                        {"Config": {"Env": ["POSTGRES_DB=dev", "POSTGRES_USER=local"]}},
                        {"Config": {"Env": env}},
                    ],
                ),
                self.assertRaises(RecoveryError),
            ):
                recovery.source_target("dev")
