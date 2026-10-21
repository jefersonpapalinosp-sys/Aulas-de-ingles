import unittest
from pathlib import Path
from unittest.mock import patch

from ops import concurrency_rollout as rollout
from ops import recovery
from ops.recovery_archive import RecoveryError


class ConcurrencyRolloutTests(unittest.TestCase):
    def test_new_clone_is_fixed_and_distinct(self):
        target = recovery.CONCURRENCY_CHECK
        self.assertEqual(recovery.DESTINATIONS[recovery.CONFIRM_CONCURRENCY_CHECK], target)
        self.assertEqual(target.project, recovery.PROJECT)
        count = len(recovery.DESTINATIONS)
        self.assertEqual(len({d.db_volume for d in recovery.DESTINATIONS.values()}), count)
        self.assertEqual(len({d.voice_volume for d in recovery.DESTINATIONS.values()}), count)

    def test_clone_cannot_access_original_network_or_storage(self):
        with (
            patch.object(recovery, "check_target") as check,
            patch.object(recovery, "quiet"),
            patch.object(recovery, "docker") as docker,
        ):
            rollout.clone_run("alembic", "upgrade", rollout.HEAD)
            check.assert_called_once_with(recovery.CONCURRENCY_CHECK)
            args = docker.call_args.args
            self.assertIn("aulas-ingles-recovery_default", args)
            self.assertNotIn("aulas-ingles-prod_default", args)
            self.assertNotIn("--mount", args)

    def test_fingerprint_preserves_all_historical_columns(self):
        queries = []

        def query(target, sql):
            queries.append(sql)
            return (
                [
                    "writing_draft",
                    "refresh_session",
                    "writing_prompt",
                    "writing_feedback",
                    "review_event",
                    "auth_rate_bucket",
                ]
                if len(queries) == 1
                else []
            )

        with patch.object(recovery, "query", side_effect=query):
            result = rollout.fingerprints(recovery.CONCURRENCY_CHECK)
        self.assertEqual(len(result), 4)
        self.assertIn("- 'revision'", queries[1])
        self.assertIn("- 'successor_jti'", queries[2])
        self.assertNotIn("- 'requirements'", queries[3])
        self.assertNotIn("- 'rubric_snapshot'", queries[4])
        self.assertTrue(all("- 'text'" not in sql for sql in queries))

    def test_refuses_wrong_schema_before_docker(self):
        for kind, revision in (("lab", [rollout.BASE]), ("prod", [rollout.HEAD])):
            with (
                patch.object(
                    rollout,
                    "verify_bundle",
                    return_value={
                        "source": {"kind": kind},
                        "snapshot": {"revision": revision},
                    },
                ),
                patch.object(recovery, "source_target") as source,
            ):
                with self.assertRaises(RecoveryError):
                    rollout.run("capture", Path("unused"))
                source.assert_not_called()

    def test_restore_receipt_requires_exact_clone_bundle_and_hash(self):
        manifest = {"bundle_id": "synthetic-bundle"}
        good = {
            "verified": True,
            "bundle_id": manifest["bundle_id"],
            "target": recovery.CONFIRM_CONCURRENCY_CHECK,
            "manifest": {"sha256": "hash"},
        }
        with (
            patch.object(rollout, "private_json", return_value=good) as read,
            patch.object(rollout, "file_info", return_value=good["manifest"]),
        ):
            rollout.validate_restore(Path("unused"), manifest)
            for key, value in (
                ("verified", False),
                ("bundle_id", "other"),
                ("target", recovery.CONFIRM_STUDY_CHECK),
                ("manifest", {}),
            ):
                read.return_value = {**good, key: value}
                with self.assertRaises(RecoveryError):
                    rollout.validate_restore(Path("unused"), manifest)

    def test_audit_refuses_inconsistent_history_without_writes(self):
        with patch.object(recovery, "query", return_value=1) as query, patch("builtins.print"):
            with self.assertRaises(RecoveryError):
                rollout.audit(recovery.CONCURRENCY_CHECK)
            self.assertEqual(query.call_count, 24)  # 22 da Sprint 38 + 2 origens `dialogue_turn`
            self.assertTrue(
                all(
                    call.args[1].lstrip().upper().startswith("SELECT")
                    for call in query.call_args_list
                )
            )

    def test_new_tables_and_columns_must_have_only_initial_state(self):
        with patch.object(recovery, "query", return_value=0):
            rollout.verify_new_state(recovery.CONCURRENCY_CHECK)
        with patch.object(recovery, "query", return_value=1), self.assertRaises(RecoveryError):
            rollout.verify_new_state(recovery.CONCURRENCY_CHECK)

    def test_legacy_exception_requires_same_counts_and_never_accepts_other_errors(self):
        report = {rule: 0 for rule in rollout.RULES}
        report.update(study_completion_timestamp=15, study_step_consistency=20)
        with patch("builtins.print"):
            with patch.object(recovery, "query", side_effect=list(report.values())):
                self.assertEqual(
                    rollout.audit(
                        recovery.CONCURRENCY_CHECK, preserve_legacy=True, expected=report
                    ),
                    report,
                )
            with (
                patch.object(recovery, "query", side_effect=list(report.values())),
                self.assertRaises(RecoveryError),
            ):
                rollout.audit(
                    recovery.CONCURRENCY_CHECK,
                    preserve_legacy=True,
                    expected={**report, "study_step_consistency": 19},
                )
            report["transcription_owner"] = 1
            with (
                patch.object(recovery, "query", side_effect=list(report.values())),
                self.assertRaises(RecoveryError),
            ):
                rollout.audit(recovery.CONCURRENCY_CHECK, preserve_legacy=True)
