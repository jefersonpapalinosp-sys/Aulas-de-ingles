import unittest
from pathlib import Path
from unittest.mock import patch

from ops import recovery, study_rollout
from ops.recovery_archive import RecoveryError


class StudyRolloutTests(unittest.TestCase):
    def test_invalid_action_stops_before_backup_or_docker(self):
        with (
            patch.object(study_rollout, "verify_bundle") as bundle,
            patch.object(recovery, "source_target") as source,
            self.assertRaises(RecoveryError),
        ):
            study_rollout.run("apply", Path("unused"))
        bundle.assert_not_called()
        source.assert_not_called()

    def test_malformed_table_inventory_precedes_dynamic_sql(self):
        for tables in (None, {}, "app_user", [None], [123], ["app_user", "app_user"]):
            with (
                self.subTest(tables=tables),
                patch.object(recovery, "query", return_value=tables) as query,
                self.assertRaises(RecoveryError),
            ):
                study_rollout.fingerprints(recovery.STUDY_CHECK)
            self.assertEqual(query.call_count, 1)

    def test_malformed_rows_cannot_produce_preservation_proof(self):
        for rows in (None, {}, "private-content", [None], ["private-content"]):
            with (
                patch.object(recovery, "query", side_effect=[["app_user"], rows]),
                self.assertRaises(RecoveryError) as raised,
            ):
                study_rollout.fingerprints(recovery.STUDY_CHECK)
            self.assertNotIn("private-content", str(raised.exception))

    def test_fingerprint_proof_validates_counts_hashes_and_fields(self):
        good = {"app_user": {"count": 1, "sha256": "a" * 64}}
        self.assertEqual(study_rollout.checked_fingerprints(good), good)
        for value in (
            None, [], {"app_user": None}, {"app_user": {}},
            {"app_user;DROP": good["app_user"]},
            {"app_user": {**good["app_user"], "extra": "unverified"}},
            *({"app_user": {**good["app_user"], "count": count}}
              for count in (-1, True, False, 0.0, "1", None)),
            *({"app_user": {**good["app_user"], "sha256": digest}}
              for digest in (None, "short", "z" * 64, 123)),
        ):
            with self.subTest(value=value), self.assertRaises(RecoveryError):
                study_rollout.checked_fingerprints(value)

    def test_fingerprint_detects_duplicate_row_count(self):
        row = {"id": 1, "text": "synthetic-private-content"}
        with patch.object(
            recovery, "query", side_effect=[["app_user"], [row], ["app_user"], [row, row]]
        ):
            before = study_rollout.fingerprints(recovery.STUDY_CHECK)
            after = study_rollout.fingerprints(recovery.STUDY_CHECK)
        self.assertEqual(before["app_user"]["count"], 1)
        self.assertEqual(after["app_user"]["count"], 2)
        self.assertNotEqual(before["app_user"]["sha256"], after["app_user"]["sha256"])
        self.assertNotIn("synthetic-private-content", str(after))

    def test_fingerprint_ignores_order_but_detects_historical_changes(self):
        target = recovery.STUDY_CHECK
        with patch.object(
            recovery,
            "query",
            side_effect=[
                ["app_user"],
                [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}],
                ["app_user"],
                [{"value": "b", "id": 2}, {"value": "a", "id": 1}],
                ["app_user"],
                [{"id": 1, "value": "different"}, {"id": 2, "value": "b"}],
            ],
        ):
            before = study_rollout.fingerprints(target)
            self.assertEqual(study_rollout.fingerprints(target), before)
            self.assertNotEqual(study_rollout.fingerprints(target), before)
            self.assertNotIn("value", str(before))

    def test_only_intended_columns_are_excluded(self):
        queries = []

        def query(target, sql):
            queries.append(sql)
            return ["writing_prompt", "writing_feedback"] if len(queries) == 1 else []

        with patch.object(recovery, "query", side_effect=query):
            study_rollout.fingerprints(recovery.STUDY_CHECK)
        self.assertIn("- 'requirements'", queries[1])
        self.assertNotIn("- 'instructions'", queries[1])
        self.assertIn("- 'algorithm_version'", queries[2])
        self.assertNotIn("- 'text'", queries[2])
        self.assertNotIn("- 'checks'", queries[2])

    def test_table_name_guard_precedes_dynamic_sql(self):
        with patch.object(recovery, "query", return_value=["app_user;DROP"]) as query:
            with self.assertRaises(RecoveryError):
                study_rollout.fingerprints(recovery.STUDY_CHECK)
            self.assertEqual(query.call_count, 1)

    def test_checksum_column_accepts_digits_without_accepting_sql(self):
        with patch.object(recovery, "query", side_effect=[["speaking_attempt"], []]) as query:
            study_rollout.fingerprints(
                recovery.STUDY_CHECK,
                excluded_columns={"speaking_attempt": ["audio_sha256"]},
            )
            self.assertIn("- 'audio_sha256'", query.call_args.args[1])
        with patch.object(recovery, "query", return_value=["speaking_attempt"]) as query:
            with self.assertRaises(RecoveryError):
                study_rollout.fingerprints(
                    recovery.STUDY_CHECK,
                    excluded_columns={"speaking_attempt": ["sha'; DROP"]},
                )
            self.assertEqual(query.call_count, 1)

    def test_clone_migration_has_no_production_network_or_storage(self):
        with (
            patch.object(recovery, "check_target") as check,
            patch.object(recovery, "quiet"),
            patch.object(recovery, "docker") as docker,
        ):
            study_rollout.clone_run("alembic", "upgrade", "head")
            check.assert_called_once_with(recovery.STUDY_CHECK)
            args = docker.call_args.args
            self.assertIn("aulas-ingles-recovery_default", args)
            self.assertNotIn("--mount", args)
            self.assertNotIn("aulas-ingles-prod_default", args)
