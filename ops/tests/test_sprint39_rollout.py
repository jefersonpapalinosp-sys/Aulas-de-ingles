import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops import recovery, roles
from ops import sprint39_rollout as rollout
from ops.assist_alignment_smoke import validate_environment
from ops.recovery_archive import RecoveryError, write_json


class Final39Tests(unittest.TestCase):
    def test_prod_configuration_reads_existing_credentials_from_secrets(self):
        target = recovery.Target("synthetic-prod", "db", "synthetic", "admin", "db", "voice", None)
        credentials = {name: "synthetic-password-0000000000000000" for name in roles.NAMES[1:]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "secrets"
            private.mkdir(mode=0o700)
            backups = root / "backups"
            backups.mkdir()
            write_json(private / "roles-prod.json", credentials)
            with (
                patch.object(roles, "SECRETS", private),
                patch.object(recovery, "BACKUPS", backups),
                patch.object(recovery, "source_target", return_value=target),
                patch.object(recovery, "container", return_value={"Config": {"Env": [
                    "DATABASE_PURPOSE=runtime", "JWT_SECRET=" + "synthetic-secret-" * 3,
                ]}}),
            ):
                config = rollout.configuration(target, "prod")
            self.assertIn("DATABASE_PURPOSE=migrator\n", config)
            self.assertIn("@db:5432/synthetic\n", config)
            self.assertIn("aulas_migrator:" + credentials["aulas_migrator"], config)
            self.assertFalse((backups / "roles-prod.json").exists())
            self.assertEqual((private / "roles-prod.json").stat().st_mode & 0o777, 0o600)

    def test_legacy_backup_file_cannot_replace_missing_private_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "roles-prod.json").write_text("legacy-placeholder")
            with (
                patch.object(roles, "SECRETS", root / "absent-secrets"),
                patch.object(recovery, "BACKUPS", root),
                patch.object(recovery, "source_target", return_value=recovery.STUDY39_CHECK),
                patch.object(recovery, "container", return_value={"Config": {
                    "Env": ["DATABASE_PURPOSE=runtime"]
                }}),
                patch.object(roles, "private_credentials") as credentials,
                self.assertRaisesRegex(RecoveryError, "Credenciais ausentes"),
            ):
                rollout.configuration(recovery.STUDY39_CHECK, "prod")
            credentials.assert_not_called()
            self.assertFalse((root / "absent-secrets").exists())

    def test_unknown_scope_is_refused_before_source_lookup(self):
        with patch.object(recovery, "source_target") as source:
            for scope in ("", "study", "../dev"):
                for operation in (rollout.configuration, rollout.fingerprints):
                    with self.assertRaises(RecoveryError):
                        operation(recovery.DEV39_CHECK, scope)
            source.assert_not_called()

    def test_clone_migration_keeps_credentials_out_of_arguments(self):
        captured = []

        def docker(*args, **kwargs):
            self.assertNotIn("restore_disposable_only", " ".join(args))
            self.assertIn(f"{recovery.PROJECT}_default", args)
            self.assertNotIn("--mount", args)
            self.assertIn("--read-only", args)
            envfile = Path(args[args.index("--env-file") + 1])
            captured.append(envfile)
            self.assertEqual(envfile.stat().st_mode & 0o777, 0o600)
            self.assertIn("@dev39-check-db:5432/aulas_ingles_restore", envfile.read_text())
            return b""

        with patch.object(recovery, "docker", side_effect=docker) as command:
            rollout.migrate(recovery.DEV39_CHECK, "dev", "sha256:synthetic", True)
        self.assertEqual(command.call_count, 3)
        self.assertTrue(all(not path.exists() for path in captured))

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
