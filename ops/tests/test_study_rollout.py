import unittest
from unittest.mock import patch

from ops import recovery, study_rollout
from ops.recovery_archive import RecoveryError


class StudyRolloutTests(unittest.TestCase):
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
