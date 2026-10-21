import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops import recovery, roles
from ops.recovery_archive import RecoveryError, file_info, write_json


class RolesGuardsTests(unittest.TestCase):
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
                receipt.write_text(json.dumps(good))
                sql.return_value = b'{"counts":{"users":2}}'
                with self.assertRaises(RecoveryError):
                    roles.backup_gate(({}, "study", "admin"), bundle)

    def test_study_restore_target_is_fixed_and_isolated(self):
        self.assertEqual(recovery.DESTINATIONS[recovery.CONFIRM_STUDY_CHECK], recovery.STUDY_CHECK)
        self.assertNotEqual(recovery.STUDY_CHECK.db_volume, recovery.RESTORE.db_volume)
        self.assertNotEqual(recovery.STUDY_CHECK.voice_volume, recovery.RESTORE.voice_volume)
        for destination in recovery.DESTINATIONS.values():
            self.assertEqual(destination.project, "aulas-ingles-recovery")
            self.assertNotIn("prod", destination.db_volume)
