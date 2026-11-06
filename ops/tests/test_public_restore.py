import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ops import public_restore, public_snapshot
from ops.recovery_archive import RecoveryError, create_bundle, verify_bundle
from ops.tests.test_public_backup import SNAPSHOT
from ops.tests.test_recovery_prune import real_capture


class PublicRestoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bundle = create_bundle(self.root / "backups", real_capture)
        self.encrypted = self.root / "copy.tar.age"
        self.identity = self.root / "key"
        self.encrypted.write_bytes(b"synthetic")
        self.identity.write_bytes(b"synthetic")

    def decrypt(self, archive):
        def run(command, **kwargs):
            kwargs["stdout"].write(archive)
            return subprocess.CompletedProcess(command, 0)

        return patch.object(public_restore.subprocess, "run", side_effect=run)

    def archive(self, *, attack=None):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            archive.add(self.bundle, arcname=self.bundle.name)
            if attack:
                archive.addfile(attack)
        return stream.getvalue()

    def test_unseal_preserves_checksums_without_extracting_archive_metadata(self):
        with self.decrypt(self.archive()):
            result = public_restore.unseal(self.encrypted, self.identity, self.root / "opened")
        self.assertEqual(verify_bundle(result), verify_bundle(self.bundle))
        self.assertEqual(result.stat().st_mode & 0o077, 0)

    def test_unseal_rejects_links_traversal_and_duplicate_members(self):
        attacks = [
            tarfile.TarInfo(self.bundle.name + "/../escape"),
            tarfile.TarInfo(self.bundle.name + "/database.dump"),
            tarfile.TarInfo(self.bundle.name + "/link"),
        ]
        attacks[2].type = tarfile.SYMTYPE
        attacks[2].linkname = "/etc/passwd"
        for index, attack in enumerate(attacks):
            with (
                self.subTest(index=index),
                self.decrypt(self.archive(attack=attack)),
                self.assertRaises(RecoveryError),
            ):
                public_restore.unseal(self.encrypted, self.identity, self.root / f"opened-{index}")
        self.assertFalse((self.root / "escape").exists())

    def test_failed_age_never_loads_database_and_existing_output_is_preserved(self):
        output = self.root / "opened"
        output.mkdir()
        with (
            patch.object(public_restore.subprocess, "run") as run,
            self.assertRaises(RecoveryError),
        ):
            public_restore.unseal(self.encrypted, self.identity, output)
        run.assert_not_called()
        with (
            patch.object(
                public_restore.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)
            ),
            self.assertRaises(RecoveryError),
        ):
            public_restore.unseal(self.encrypted, self.identity, self.root / "failed")

    def test_destination_rejects_running_application(self):
        destination = public_restore.Destination("local", "aulas-dr-test")
        db = [
            True,
            {"com.docker.compose.project": destination.project, "com.docker.compose.service": "db"},
            [
                {
                    "Type": "volume",
                    "Name": "aulas-dr-test_pgdata",
                    "Destination": "/var/lib/postgresql/data",
                }
            ],
            "sha256:" + "a" * 64,
        ]
        api = [
            True,
            {
                "com.docker.compose.project": destination.project,
                "com.docker.compose.service": "api",
            },
            [],
            "sha256:" + "b" * 64,
        ]
        responses = [
            "\n".join(map(json.dumps, db)).encode(),
            json.dumps({"com.docker.compose.project": destination.project}).encode(),
            "\n".join(map(json.dumps, api)).encode(),
        ]
        with (
            patch.object(destination, "call", side_effect=responses),
            self.assertRaises(RecoveryError),
        ):
            destination.check()

    def test_exported_snapshot_lives_until_dump_finishes_then_releases_session(self):
        process = MagicMock()
        process.stdin = io.BytesIO()
        process.stdout = io.BytesIO(
            json.dumps({"token": "000001-000002-1", "snapshot": SNAPSHOT}).encode() + b"\n"
        )
        process.poll.return_value = None
        with patch.object(public_snapshot.subprocess, "Popen", return_value=process):
            with public_snapshot.exported_snapshot("local") as (snapshot, token):
                self.assertEqual(snapshot, SNAPSHOT)
                self.assertEqual(token, "000001-000002-1")
                process.communicate.assert_not_called()
            process.communicate.assert_called_once_with(timeout=5)
        self.assertIn(b"REPEATABLE READ READ ONLY", process.stdin.getvalue())

    def test_exported_snapshot_rejects_session_that_died_during_dump(self):
        process = MagicMock()
        process.stdin = io.BytesIO()
        process.stdout = io.BytesIO(
            json.dumps({"token": "000001-000002-1", "snapshot": SNAPSHOT}).encode() + b"\n"
        )
        process.poll.return_value = 1
        with (
            patch.object(public_snapshot.subprocess, "Popen", return_value=process),
            self.assertRaises(RecoveryError),
            public_snapshot.exported_snapshot("local"),
        ):
            pass
        process.communicate.assert_called_once()
