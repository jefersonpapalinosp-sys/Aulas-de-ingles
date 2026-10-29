import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops import recovery, roles
from ops.recovery_archive import RecoveryError, file_info, write_json


class RolesGuardsTests(unittest.TestCase):
    def test_credentials_validate_structure_without_disclosing_values(self):
        credentials = {name: "synthetic-private-password-000000000" for name in roles.NAMES[1:]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "roles-lab.json"
            write_json(path, credentials)
            with patch.object(roles, "SECRETS", root):
                self.assertEqual(roles.private_credentials("lab"), credentials)
                for value in (
                    None, [], list(credentials), "private-value", 3,
                    {**credentials, "unexpected": "private-value"},
                    {**credentials, "aulas_runtime": 123},
                    {**credentials, "aulas_runtime": "private-value"},
                    {**credentials, "aulas_runtime": "private-value'" * 4},
                    {**credentials, "aulas_runtime": "privá" * 10},
                ):
                    with self.subTest(value=type(value).__name__):
                        path.write_text(json.dumps(value))
                        with self.assertRaises(RecoveryError) as raised:
                            roles.private_credentials("lab")
                        self.assertEqual(str(raised.exception), "Credenciais inválidas.")

    def test_credentials_refuse_links_and_public_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "roles-lab.json"
            original = root / "original.json"
            write_json(
                original,
                {name: "synthetic-password-0000000000000000" for name in roles.NAMES[1:]},
            )
            with patch.object(roles, "SECRETS", root):
                path.symlink_to(original)
                with self.assertRaises(RecoveryError):
                    roles.private_credentials("lab")
                path.unlink()
                path.write_bytes(original.read_bytes())
                path.chmod(0o644)
                with self.assertRaises(RecoveryError):
                    roles.private_credentials("lab")

    def test_unknown_scope_or_role_fails_before_resource_access(self):
        with (
            patch.object(roles, "secrets_dir") as directory,
            patch.object(recovery, "local_daemon") as daemon,
        ):
            for scope in ("", "../outside", "other"):
                for operation in (roles.target, roles.private_credentials):
                    with self.assertRaises(RecoveryError):
                        operation(scope)
            directory.assert_not_called()
            daemon.assert_not_called()
        with patch.object(roles, "target") as target:
            for purpose in ("owner", "admin", "../runtime", ""):
                with self.assertRaises(RecoveryError):
                    roles.lab_run(purpose, "unused")
            target.assert_not_called()

    def test_malformed_inventory_blocks_provision_before_credentials(self):
        good = {"name": "aulas_runtime", "marker": roles.MARKER}
        for value in (None, {}, [None], [{}], [{**good, "name": "unrelated"}], [good, good]):
            with (
                self.subTest(value=value),
                patch.object(roles, "target", return_value=({}, "lab", "admin")),
                patch.object(roles, "sql", return_value=json.dumps(value).encode()) as sql,
                patch.object(roles, "private_credentials") as credentials,
                self.assertRaises(RecoveryError),
            ):
                roles.provision("lab")
            credentials.assert_not_called()
            self.assertEqual(sql.call_count, 1)  # Somente leitura do inventário.
        with patch.object(roles, "sql", return_value=json.dumps([good]).encode()):
            self.assertEqual(roles.marked_roles(({}, "lab", "admin")), [good])

    def test_sql_uses_stdin_instead_of_process_arguments(self):
        statement = "SELECT 'synthetic-private-value'"

        def docker(*args, **kwargs):
            self.assertNotIn(statement, args)
            self.assertEqual(kwargs["stdin"].read(), statement.encode())
            self.assertEqual(args[args.index("-U") + 1], "aulas_backup")
            return b"synthetic-result"

        with patch.object(recovery, "docker", side_effect=docker):
            self.assertEqual(
                roles.sql(({"Id": "container"}, "lab", "admin"), statement, "aulas_backup"),
                b"synthetic-result",
            )

    def test_provision_preserves_env_when_json_keys_are_reordered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credentials = {
                name: "synthetic-credential-000000000000000000" for name in roles.NAMES[1:]
            }
            write_json(root / "roles-lab.json", credentials)
            with (
                patch.object(roles, "SECRETS", root),
                patch.object(roles, "target", return_value=({}, "aulas_roles_lab", "admin")),
                patch.object(roles, "marked_roles", return_value=[]),
                patch.object(roles, "sql"),
                patch.object(roles, "private_credentials", return_value=credentials) as private,
            ):
                roles.provision("lab")
                original = (root / "roles-lab.env").read_bytes()
                private.return_value = dict(reversed(list(credentials.items())))
                roles.provision("lab")
                self.assertEqual((root / "roles-lab.env").read_bytes(), original)

    def test_invalid_scope_refused_before_resource_access(self):
        with patch.object(recovery, "local_daemon"), patch.object(roles, "resources") as resources:
            with self.assertRaises(RecoveryError):
                roles.target("other")
            resources.assert_not_called()

    def test_production_provision_and_grants_require_verified_backup(self):
        for operation in (roles.provision, roles.grants):
            with (
                patch.object(roles, "target", return_value=({}, "study", "admin")),
                patch.object(roles, "sql") as sql,
            ):
                with self.assertRaises(RecoveryError):
                    operation("prod")
                sql.assert_not_called()

    def test_unmarked_roles_refused_before_credentials_or_writes(self):
        with (
            patch.object(roles, "target", return_value=({}, "lab", "admin")),
            patch.object(
                roles, "sql", return_value=b'[{"name":"aulas_owner","marker":null}]'
            ) as sql,
            patch.object(roles, "private_credentials") as credentials,
        ):
            with self.assertRaises(RecoveryError):
                roles.provision("lab")
            credentials.assert_not_called()
            self.assertEqual(sql.call_count, 1)

    def test_receipt_must_match_bundle_target_hash_and_current_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            bundle.mkdir()
            (bundle / "manifest.json").write_text('{"synthetic":true}')
            receipt = root / "restore-receipts" / "bundle.json"
            receipt.parent.mkdir()
            manifest = {
                "bundle_id": "bundle",
                "source": {"kind": "prod", "database": "study"},
                "snapshot": {"counts": {"users": 1}},
            }
            good = {
                "verified": True,
                "bundle_id": "bundle",
                "target": recovery.CONFIRM_STUDY_CHECK,
                "manifest": file_info(bundle / "manifest.json"),
            }
            write_json(receipt, good)
            with (
                patch.object(recovery, "BACKUPS", root),
                patch.object(roles, "verify_bundle", return_value=manifest),
                patch.object(
                    roles, "sql", return_value=json.dumps(manifest["snapshot"]).encode()
                ) as sql,
            ):
                roles.backup_gate(({}, "study", "admin"), bundle)
                for key, value in (
                    ("verified", False),
                    ("bundle_id", "wrong"),
                    ("target", recovery.CONFIRM_TARGET),
                    ("manifest", {}),
                ):
                    receipt.write_text(json.dumps({**good, key: value}))
                    with self.assertRaises(RecoveryError):
                        roles.backup_gate(({}, "study", "admin"), bundle)
                for value in (None, [], 1, "private-value"):
                    receipt.write_text(json.dumps(value))
                    sql.reset_mock()
                    with self.assertRaises(RecoveryError):
                        roles.backup_gate(({}, "study", "admin"), bundle)
                    sql.assert_not_called()
                receipt.write_text(json.dumps(good))
                sql.return_value = b'{"counts":{"users":2}}'
                with self.assertRaises(RecoveryError):
                    roles.backup_gate(({}, "study", "admin"), bundle)

    def test_invalid_backup_source_fails_before_query(self):
        for source in (None, [], "private-value", {}, {"kind": "dev", "database": "study"}):
            with (
                patch.object(roles, "verify_bundle", return_value={"source": source}),
                patch.object(roles, "sql") as sql,
                self.assertRaises(RecoveryError),
            ):
                roles.backup_gate(({}, "study", "admin"), Path("unused"))
            sql.assert_not_called()

    def test_study_restore_target_is_fixed_and_isolated(self):
        self.assertEqual(recovery.DESTINATIONS[recovery.CONFIRM_STUDY_CHECK], recovery.STUDY_CHECK)
        self.assertNotEqual(recovery.STUDY_CHECK.db_volume, recovery.RESTORE.db_volume)
        self.assertNotEqual(recovery.STUDY_CHECK.voice_volume, recovery.RESTORE.voice_volume)
        for destination in recovery.DESTINATIONS.values():
            self.assertEqual(destination.project, "aulas-ingles-recovery")
            self.assertNotIn("prod", destination.db_volume)
