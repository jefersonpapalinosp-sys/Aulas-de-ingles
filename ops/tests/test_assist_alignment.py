import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from ops import assist_alignment as alignment
from ops import dev_alignment, recovery
from ops.assist_alignment_smoke import validate_environment
from ops.recovery_archive import RecoveryError


class AssistAlignmentTests(unittest.TestCase):
    def test_existing_smoke_receipt_never_repeats_writes_and_rejects_stale_script(self):
        manifest = {
            "source": {"kind": "dev", "project": "aulas-ingles"},
            "snapshot": {"revision": [alignment.BASE]},
            "bundle_id": "fixture",
        }
        receipt = {
            "verified": True,
            "revision": alignment.HEAD,
            "target": recovery.CONFIRM_ASSIST_CHECK,
            "manifest": "hash",
            "tools_image": "image",
            "smoke_script": "hash",
            "http": {
                "verified": True,
                "mode": "http-clone",
                "checks": 11,
                "synthetic_user_remaining": 0,
                "provider_calls": 0,
            },
        }
        proof = {"manifest": "hash", "tools_image": "image", "tables": {}}
        for stale in (False, True):
            with (
                self.subTest(stale=stale),
                patch.object(alignment, "verify_bundle", return_value=manifest),
                patch.object(alignment, "file_info", return_value="hash"),
                patch.object(dev_alignment, "image_id", return_value="image"),
                patch.object(
                    alignment.concurrency_rollout,
                    "private_json",
                    side_effect=[
                        receipt,
                        proof,
                        {**receipt, "smoke_script": "changed" if stale else "hash"},
                    ],
                ),
                patch.object(recovery, "check_target"),
                patch.object(recovery, "quiet"),
                patch.object(recovery, "lease", return_value=nullcontext()),
                patch.object(recovery, "query", return_value={"revision": [alignment.HEAD]}),
                patch.object(alignment, "fingerprints", return_value={}),
                patch.object(alignment, "verify_backfill"),
                patch.object(dev_alignment, "verify_voice"),
                patch.object(Path, "exists", return_value=True),
                patch.object(recovery, "docker") as docker,
                patch("builtins.print"),
                self.assertRaises(RecoveryError) if stale else nullcontext(),
            ):
                alignment.smoke_clone(Path("unused"))
            docker.assert_not_called()

    def test_smoke_receipt_binds_script_and_all_checks(self):
        good = {
            "verified": True,
            "revision": alignment.HEAD,
            "target": recovery.CONFIRM_ASSIST_CHECK,
            "manifest": "backup",
            "tools_image": "image",
            "smoke_script": "script",
            "http": {
                "verified": True,
                "mode": "http-clone",
                "checks": 11,
                "synthetic_user_remaining": 0,
                "provider_calls": 0,
            },
        }
        with patch.object(alignment, "file_info", return_value="script"):
            alignment.validate_smoke_receipt(good, manifest_hash="backup", tools_image="image")
            for key, value in (
                ("checks", 9),
                ("provider_calls", 1),
                ("synthetic_user_remaining", 1),
                ("mode", "http-dev"),
                ("verified", False),
            ):
                with self.subTest(key=key), self.assertRaises(RecoveryError):
                    alignment.validate_smoke_receipt(
                        {**good, "http": {**good["http"], key: value}},
                        manifest_hash="backup",
                        tools_image="image",
                    )
        with (
            patch.object(alignment, "file_info", return_value="changed"),
            self.assertRaises(RecoveryError),
        ):
            alignment.validate_smoke_receipt(good, manifest_hash="backup", tools_image="image")

    def test_smoke_refuses_provider_and_wrong_environment_before_app_import(self):
        env = {
            "APP_ENV": "dev",
            "ASSISTED_FEATURES_ENABLED": "false",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@assist-check-db/aulas_ingles_restore",
        }
        validate_environment(env, live=False)
        for field, value in (
            ("APP_ENV", "prod"),
            ("DATABASE_PURPOSE", "runtime"),
            ("ASSISTED_FEATURES_ENABLED", "true"),
            ("DATABASE_URL", "postgresql+asyncpg://user:pass@db/aulas_ingles_restore"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_environment({**env, field: value}, live=False)

    def test_refuses_wrong_source_and_revision_before_docker(self):
        for kind, project, revision in (
            ("prod", "aulas-ingles-prod", alignment.BASE),
            ("lab", recovery.PROJECT, alignment.BASE),
            ("dev", "aulas-ingles-prod", alignment.BASE),
            ("dev", "aulas-ingles", alignment.HEAD),
        ):
            with (
                self.subTest(kind=kind, project=project, revision=revision),
                patch.object(
                    alignment,
                    "verify_bundle",
                    return_value={
                        "source": {"kind": kind, "project": project},
                        "snapshot": {"revision": [revision]},
                    },
                ),
                patch.object(recovery, "source_target") as source,
                self.assertRaises(RecoveryError),
            ):
                alignment.run("apply", Path("unused"))
            source.assert_not_called()

    def test_preserves_earlier_sprint_tables_and_columns(self):
        with patch.object(alignment.study_rollout, "fingerprints") as fingerprint:
            alignment.fingerprints(recovery.ASSIST_CHECK)
        self.assertEqual(
            fingerprint.call_args.kwargs,
            {
                "excluded_tables": ("assist_reservation",),
                "excluded_columns": {
                    "writing_feedback": ["assist_reservation_id"],
                    "transcription_job": ["assist_reservation_id"],
                },
            },
        )

    def test_clone_is_distinct_without_touching_previous_restores(self):
        self.assertEqual(
            recovery.DESTINATIONS[recovery.CONFIRM_ASSIST_CHECK], recovery.ASSIST_CHECK
        )
        targets = list(recovery.DESTINATIONS.values())
        self.assertEqual(len(targets), len({t.db_volume for t in targets}))
        self.assertEqual(len(targets), len({t.voice_volume for t in targets}))
        self.assertTrue(all(t.project == recovery.PROJECT for t in targets))

    def test_receipt_cannot_reuse_previous_sprint_or_changed_image(self):
        good = {
            "verified": True,
            "revision": alignment.HEAD,
            "target": recovery.CONFIRM_ASSIST_CHECK,
            "manifest": {"sha256": "backup"},
            "tools_image": "sha256:immutable",
        }
        for key, value in (
            ("verified", False),
            ("revision", alignment.BASE),
            ("target", recovery.CONFIRM_DEV_CHECK),
            ("manifest", {}),
            ("tools_image", "changed"),
        ):
            with self.subTest(field=key), self.assertRaises(RecoveryError):
                alignment.validate_receipt(
                    {**good, key: value},
                    manifest_hash=good["manifest"],
                    tools_image=good["tools_image"],
                )
        alignment.validate_receipt(
            good, manifest_hash=good["manifest"], tools_image=good["tools_image"]
        )

    def test_migration_uses_only_dedicated_network_no_mount_or_seed(self):
        with (
            patch.object(recovery, "check_target"),
            patch.object(recovery, "quiet"),
            patch.object(recovery, "docker") as docker,
        ):
            dev_alignment.run_migration(
                recovery.ASSIST_CHECK,
                "sha256:immutable",
                head=alignment.HEAD,
                clone=recovery.ASSIST_CHECK,
            )
        self.assertEqual(docker.call_count, 3)
        for call in docker.call_args_list:
            self.assertIn(f"{recovery.PROJECT}_default", call.args)
            self.assertIn("sha256:immutable", call.args)
            self.assertNotIn("--mount", call.args)
            self.assertNotIn("seed", call.args)

    def test_unapproved_migration_clone_pair_refused_before_target_lookup(self):
        with (
            patch.object(recovery, "source_target") as source,
            self.assertRaises(RecoveryError),
        ):
            dev_alignment.run_migration(recovery.DEV_CHECK, "image", head=alignment.HEAD)
        source.assert_not_called()

    def test_backfill_checks_both_directions_and_non_assisted_links(self):
        with patch.object(recovery, "query", return_value=0) as query:
            alignment.verify_backfill(recovery.ASSIST_CHECK)
        sql = query.call_args.args[1]
        self.assertEqual(sql.count("EXCEPT ALL"), 2)
        self.assertIn("provider IS NULL AND assist_reservation_id IS NOT NULL", sql)
        with (
            patch.object(recovery, "query", return_value=1),
            self.assertRaises(RecoveryError),
        ):
            alignment.verify_backfill(recovery.ASSIST_CHECK)

    def test_apply_needs_rehearsal_and_preservation_before_any_migration(self):
        target = recovery.Target("aulas-ingles", "db", "dev", "app", "db", "voice", None)
        manifest = {
            "source": {
                "kind": "dev",
                "project": "aulas-ingles",
                "database": "dev",
                "db_container_id": "id",
                "voice_volume": "voice",
            },
            "snapshot": {"revision": [alignment.BASE]},
            "bundle_id": "fixture",
        }
        proof = {
            "manifest": "hash",
            "tools_image": "image",
            "tables": {"old": {"count": 1}},
        }
        for changed in (False, True):
            with (
                self.subTest(changed=changed),
                patch.object(alignment, "verify_bundle", return_value=manifest),
                patch.object(alignment, "file_info", return_value="hash"),
                patch.object(recovery, "source_target", return_value=target),
                patch.object(recovery, "check_target", return_value={"Id": "id"}),
                patch.object(recovery, "quiet"),
                patch.object(recovery, "lease", return_value=nullcontext()),
                patch.object(recovery, "query", return_value=manifest["snapshot"]),
                patch.object(dev_alignment, "image_id", return_value="image"),
                patch.object(dev_alignment, "verify_voice"),
                patch.object(
                    alignment,
                    "fingerprints",
                    return_value={} if changed else proof["tables"],
                ),
                patch.object(
                    alignment.concurrency_rollout,
                    "private_json",
                    side_effect=[proof, {}],
                ),
                patch.object(dev_alignment, "run_migration") as migration,
                patch.object(alignment, "write_json") as receipt,
                self.assertRaises(RecoveryError),
            ):
                alignment.run("apply", Path("unused"))
            migration.assert_not_called()
            receipt.assert_not_called()
