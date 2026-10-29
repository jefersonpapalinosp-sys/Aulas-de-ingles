"""Backup público sem SSH real: comandos remotos simulados, formato v2 verificado de verdade."""

import io
import json
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ops import public_backup, recovery
from ops.recovery_archive import RecoveryError, verify_bundle

KEY = "00000000000000000000000000000001.wav"
PAYLOAD = b"synthetic-public-audio"
SNAPSHOT = {
    "revision": ["d2b7e4c9a150"],
    "counts": {"users": 1, "lessons": 82, "speaking": 1},
    "audio": [{"id": 1, "key": KEY, "size": len(PAYLOAD), "status": "ready"}],
}
INSPECT = "\n".join(
    f"{i:064x} sha256:{i:064x} papalino_aulas-ingles-{service}:latest"
    for i, service in enumerate(("db", "api", "worker"), start=1)
)


def voice_tar():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo(KEY)
        member.size = len(PAYLOAD)
        archive.addfile(member, io.BytesIO(PAYLOAD))
    return buffer.getvalue()


class FakeRemote:
    """Despacha pelo conteúdo do comando remoto e registra tudo o que foi pedido."""

    def __init__(self, snapshots=None):
        self.snapshots = list(snapshots or [SNAPSHOT, SNAPSHOT])
        self.commands = []
        self.copies = []

    def ssh(self, host, remote, *, stdin=None, stdout=None, timeout=600):
        self.commands.append(remote)
        if "docker inspect" in remote:
            return INSPECT.encode()
        if "pg_dump" in remote:
            stdout.write(b"PGDMP-synthetic-custom-format")
            return b""
        if "voice_transfer.py export" in remote:
            stdout.write(voice_tar())
            return b""
        if "current_database()" in remote:
            return b"aulas_ingles\n"
        if "psql" in remote:
            value = self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]
            return json.dumps(value).encode()
        return b""

    def scp(self, host, sources, remote_dir):
        self.copies.append((tuple(Path(s).name for s in sources), remote_dir))


class PublicBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "recovery"
        self.root.mkdir(mode=0o700)
        self.remote = FakeRemote()
        patches = [
            patch.object(recovery, "BACKUPS", self.root),
            patch.object(recovery, "local_daemon"),
            patch.object(public_backup, "ssh", self.remote.ssh),
            patch.object(public_backup, "scp", self.remote.scp),
            patch.object(public_backup, "local_pg_restore_list"),
            patch.object(
                public_backup,
                "worktree_info",
                return_value={"worktree_head": "test", "worktree_dirty": False},
            ),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_capture_publishes_verifiable_v2_bundle_and_receipt_without_secrets(self):
        bundle = public_backup.capture("root@vm.test")
        manifest = verify_bundle(bundle)
        self.assertEqual(manifest["source"]["kind"], "public")
        self.assertEqual(manifest["source"]["database"], "aulas_ingles")
        self.assertEqual(manifest["source"]["consistency"], "online-snapshot-check")
        self.assertEqual(manifest["snapshot"], SNAPSHOT)
        self.assertEqual(
            [c["service"] for c in manifest["application"]["deployed_containers"]],
            ["api", "worker"],
        )
        self.assertEqual(sorted(manifest["audio_files"]), [KEY])
        receipt = public_backup.write_receipt(manifest)
        text = receipt.read_text(encoding="utf-8")
        self.assertIn(manifest["bundle_id"], text)
        for forbidden in ("PASSWORD", "password", "@", "DATABASE_URL"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(receipt.stat().st_mode & 0o077, 0)
        self.assertFalse([p for p in self.root.iterdir() if p.name.startswith(".partial-")])

    def test_remote_commands_use_backup_role_and_never_touch_passwords(self):
        public_backup.capture("root@vm.test")
        joined = "\n".join(self.remote.commands)
        self.assertIn("pg_dump -U aulas_backup", joined)
        self.assertIn("psql -U aulas_backup", joined)
        self.assertNotIn("POSTGRES_PASSWORD", joined)
        self.assertNotIn("aulas_admin", joined)
        export = next(c for c in self.remote.commands if "voice_transfer.py export" in c)
        for flag in ("--network none", "--read-only", "--cap-drop ALL", "--user 10001:10001"):
            self.assertIn(flag, export)
        self.assertIn("dst=/voice,readonly", export)
        self.assertEqual(self.remote.copies[0][0], ("recovery_archive.py", "voice_transfer.py"))
        self.assertTrue(
            any(
                c.startswith("rm -rf /tmp/aulas-ingles-backup-tools-") for c in self.remote.commands
            )
        )

    def test_snapshot_drift_blocks_publication_after_retries(self):
        drifted = {**SNAPSHOT, "counts": {**SNAPSHOT["counts"], "users": 2}}
        # before/after divergem em todas as tentativas: nunca publica.
        self.remote.snapshots = [SNAPSHOT, drifted] * 3 + [SNAPSHOT]
        with self.assertRaises(RecoveryError) as error:
            public_backup.capture("root@vm.test", attempts=3)
        self.assertEqual(str(error.exception), public_backup.DRIFT)
        published = [p for p in self.root.iterdir() if not p.name.startswith(".partial-")]
        self.assertEqual(published, [])
        self.assertEqual(len([p for p in self.root.iterdir() if p.name.startswith(".partial-")]), 3)

    def test_snapshot_drift_recovers_on_a_later_attempt(self):
        drifted = {**SNAPSHOT, "counts": {**SNAPSHOT["counts"], "users": 2}}
        self.remote.snapshots = [SNAPSHOT, drifted, SNAPSHOT, SNAPSHOT]
        bundle = public_backup.capture("root@vm.test", attempts=2)
        self.assertEqual(verify_bundle(bundle)["snapshot"], SNAPSHOT)

    def test_inventory_requires_all_three_containers(self):
        self.remote.ssh = lambda *a, **k: b"only one line\n"
        with (
            patch.object(public_backup, "ssh", self.remote.ssh),
            self.assertRaises(RecoveryError),
        ):
            public_backup.inventory("root@vm.test")

    def test_ssh_is_batch_mode_with_strict_host_keys(self):
        options = " ".join(public_backup.SSH_OPTIONS)
        self.assertIn("BatchMode=yes", options)
        self.assertIn("StrictHostKeyChecking=yes", options)
        self.assertNotIn("accept-new", options)

    def test_host_resolution_validates_shape(self):
        self.assertEqual(public_backup.resolve_host("deploy@vm.example"), "deploy@vm.example")
        with patch.dict("os.environ", {public_backup.HOST_ENV: "ops@10.0.0.5"}):
            self.assertEqual(public_backup.resolve_host(), "ops@10.0.0.5")
        for bad in ("vm.example", "root@vm.example; rm -rf /", "a b@c"):
            with self.assertRaises(RecoveryError):
                public_backup.resolve_host(bad)

    def test_encrypt_requires_age_tool_and_valid_recipient(self):
        bundle = public_backup.capture("root@vm.test")
        recipient_file = Path(self.tmp.name) / "recipient.txt"
        recipient_file.write_text("age1" + "q" * 58 + "\n")
        with (
            patch.object(public_backup.shutil, "which", return_value=None),
            self.assertRaises(RecoveryError) as error,
        ):
            public_backup.encrypt(
                bundle, public_backup.read_recipient(recipient_file), self.root.parent / "enc"
            )
        self.assertIn("age", str(error.exception))
        recipient_file.write_text("ssh-rsa AAAA\n")
        with self.assertRaises(RecoveryError):
            public_backup.read_recipient(recipient_file)

    def test_external_copy_refuses_plaintext_bundles(self):
        plain = Path(self.tmp.name) / "aulas-x.tar"
        plain.write_bytes(b"not encrypted")
        destination = Path(self.tmp.name) / "external"
        destination.mkdir()
        with self.assertRaises(RecoveryError):
            public_backup.copy_external(plain, destination)
        self.assertEqual(list(destination.iterdir()), [])

    def test_cli_refuses_external_copy_without_recipient(self):
        with patch.object(public_backup, "capture") as capture:
            code = public_backup.main(["capture", "--copy-to", self.tmp.name])
        self.assertEqual(code, 1)
        capture.assert_not_called()

    def test_check_reports_identity_without_capturing(self):
        with patch.object(public_backup, "create_bundle") as create:
            report = public_backup.check("root@vm.test")
        create.assert_not_called()
        self.assertEqual(report["revision"], SNAPSHOT["revision"])
        self.assertEqual(report["database"], "aulas_ingles")
        self.assertEqual(report["backup_role"], "aulas_backup")
        self.assertEqual(
            set(report["containers"]),
            {
                "papalino_aulas-ingles-db-1",
                "papalino_aulas-ingles-api-1",
                "papalino_aulas-ingles-worker-1",
            },
        )

    def test_invalid_snapshot_never_starts_dump_or_publishes_bundle(self):
        for bad in (
            None, [], {"revision": ["v"]},
            {**SNAPSHOT, "revision": "private"},
            {**SNAPSHOT, "revision": [1]},
            {**SNAPSHOT, "counts": {"users": True}},
            {**SNAPSHOT, "counts": {"users": -1}},
            {**SNAPSHOT, "audio": ["private"]},
        ):
            with self.subTest(bad=bad):
                self.remote.snapshots = [bad]
                self.remote.commands.clear()
                with self.assertRaises(RecoveryError) as error:
                    public_backup.capture("root@vm.test")
                self.assertNotIn("private", str(error.exception))
                self.assertFalse(any("pg_dump" in command for command in self.remote.commands))
                self.assertEqual(list(self.root.glob("aulas-*")), [])

    def test_snapshot_extensions_are_preserved_in_drift_comparison(self):
        self.remote.snapshots = [
            {**SNAPSHOT, "extension": {"value": 1}},
            {**SNAPSHOT, "extension": {"value": 2}},
        ]
        with self.assertRaisesRegex(RecoveryError, public_backup.DRIFT):
            public_backup.capture("root@vm.test", attempts=1)
        self.assertEqual(list(self.root.glob("aulas-*")), [])

    def test_invalid_receipt_metadata_does_not_create_receipt_directory(self):
        for manifest in ({}, {"snapshot": SNAPSHOT, "audio_files": [], "application": {}}):
            with self.assertRaises(RecoveryError):
                public_backup.write_receipt(manifest)
        self.assertFalse(public_backup.receipts_dir().exists())

    def test_cli_local_capture_and_preflight_render_typed_reports(self):
        for arguments in (["check"], ["check", "--json"], ["capture"], ["capture", "--json"]):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(public_backup.main(arguments), 0)
            self.assertNotIn("DATABASE_URL", output.getvalue())
            if "--json" in arguments:
                report = json.loads(output.getvalue())
                self.assertEqual(report["revision"], SNAPSHOT["revision"])

    def test_cli_capture_failure_does_not_announce_success(self):
        self.remote.snapshots = [{"revision": "private"}]
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(public_backup.main(["capture", "--json"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("private", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
