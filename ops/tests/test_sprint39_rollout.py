import unittest
from unittest.mock import patch

from ops import recovery
from ops import sprint39_rollout as rollout
from ops.assist_alignment_smoke import validate_environment
from ops.recovery_archive import RecoveryError


class Final39Tests(unittest.TestCase):
    def test_receipt_requires_same_image_backup_scripts_clone_and_http(self):
        binding = {
            "manifest": "backup",
            "tools_image": "immutable",
            "smoke_script": "s",
            "rollout_script": "r",
        }
        receipt = {
            **binding,
            "verified": True,
            "revision": rollout.HEAD,
            "target": recovery.CONFIRM_DEV39_CHECK,
            "http": {
                "verified": True,
                "mode": "http-clone",
                "checks": 11,
                "synthetic_user_remaining": 0,
                "provider_calls": 0,
            },
        }
        rollout.validate_receipt(receipt, binding, recovery.DEV39_CHECK)
        for key in (*binding, "target", "revision", "http", "verified"):
            with self.subTest(key=key), self.assertRaises(RecoveryError):
                rollout.validate_receipt({**receipt, key: "wrong"}, binding, recovery.DEV39_CHECK)

    def test_existing_39f_ledger_is_not_excluded_from_dev_proof(self):
        with patch.object(rollout.study_rollout, "fingerprints") as fp:
            rollout.fingerprints(recovery.DEV39_CHECK, "dev")
            self.assertNotIn("assist_reservation", fp.call_args.kwargs["excluded_tables"])
            self.assertEqual(set(fp.call_args.kwargs["excluded_columns"]), {"speaking_attempt"})
            rollout.fingerprints(recovery.STUDY39_CHECK, "prod")
            self.assertNotIn("writing_draft", fp.call_args.kwargs["excluded_columns"])
            self.assertNotIn(
                "algorithm_version",
                fp.call_args.kwargs["excluded_columns"]["writing_feedback"],
            )

    def test_clones_are_distinct_and_wrong_target_refused(self):
        self.assertNotEqual(recovery.DEV39_CHECK.voice_volume, recovery.STUDY39_CHECK.voice_volume)
        self.assertNotEqual(recovery.DEV39_CHECK.db_volume, recovery.DEV_CHECK.db_volume)
        with self.assertRaises(RecoveryError):
            rollout.configuration(recovery.LAB, "dev", True)

    def test_study_smoke_requires_explicit_flag_and_runtime(self):
        env = {
            "APP_ENV": "prod",
            "DATABASE_PURPOSE": "runtime",
            "ASSISTED_FEATURES_ENABLED": "false",
            "DATABASE_URL": "postgresql+asyncpg://aulas_runtime:fake@db/aulas_ingles",
        }
        validate_environment(env, live=True, study=True)
        with self.assertRaises(ValueError):
            validate_environment(env, live=True)
        with self.assertRaises(ValueError):
            validate_environment(env, live=False, study=True)
        with self.assertRaises(ValueError):
            validate_environment({**env, "DATABASE_PURPOSE": "migrator"}, live=True, study=True)
