import copy
import io
import json
import tarfile
import tempfile
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ops import recovery
from ops.recovery_archive import (
    LEGACY_FORMAT,
    MAX_AUDIO,
    RecoveryError,
    audio_inventory,
    check_references,
    create_bundle,
    verify_bundle,
)

KEY = "00000000000000000000000000000001.wav"
PAYLOAD = b"synthetic-audio-for-unit-test"
SNAPSHOT = {
    "revision": ["test-revision"],
    "counts": {"users": 1, "speaking": 1},
    "audio": [{"id": 1, "key": KEY, "size": len(PAYLOAD), "status": "ready"}],
}


def write_tar(path, entries=None):
    with tarfile.open(path, "w") as archive:
        for name, payload, kind in entries or [(KEY, PAYLOAD, tarfile.REGTYPE)]:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(payload) if kind == tarfile.REGTYPE else 0
            member.linkname = "../../outside" if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ""
            archive.addfile(member, io.BytesIO(payload))


def capture(path):
    (path / "database.dump").write_bytes(b"synthetic-custom-dump")
    write_tar(path / "voice.tar")
    return {
        "snapshot": SNAPSHOT,
        "source": {"kind": "lab"},
        "application": {"worktree_head": "test"},
    }


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_complete_package_private_and_verifiable(self):
        bundle = create_bundle(self.root, capture)
        manifest = verify_bundle(bundle)
        self.assertEqual(manifest["snapshot"], SNAPSHOT)
        self.assertEqual(manifest["audio_files"][KEY]["size"], len(PAYLOAD))
        self.assertEqual(bundle.stat().st_mode & 0o777, 0o700)
        for path in bundle.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_two_backups_same_clock_do_not_collide(self):
        with patch("ops.recovery_archive.datetime") as clock:
            clock.now.return_value.strftime.return_value = "20261013T120000000000Z"
            clock.now.return_value.isoformat.return_value = "2026-10-13T12:00:00Z"
            first = create_bundle(self.root, capture)
            second = create_bundle(self.root, capture)
        self.assertNotEqual(first, second)
        self.assertEqual(verify_bundle(first)["snapshot"], verify_bundle(second)["snapshot"])

    def test_pg_dump_failure_has_nonzero_exit_no_success_or_published_package(self):
        def fail(path):
            (path / "database.dump").write_bytes(b"truncated")
            raise RecoveryError("pg_dump falhou")

        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(recovery, "backup", side_effect=lambda _: create_bundle(self.root, fail)),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            self.assertEqual(recovery.main(["backup", "--source", "lab"]), 1)
        self.assertNotIn("publicado", output.getvalue())
        self.assertFalse(list(self.root.glob("aulas-*")))
        self.assertEqual(len(list(self.root.glob(".partial-*"))), 1)
        self.assertIn("recusada", errors.getvalue())

    def test_corrupt_dump_missing_file_and_audio_tamper_rejected(self):
        for change in ("database.dump", "voice.tar", "missing"):
            with self.subTest(change=change):
                bundle = create_bundle(self.root, capture)
                if change == "missing":
                    (bundle / "voice.tar").unlink()
                else:
                    with (bundle / change).open("ab") as stream:
                        stream.write(b"tampered")
                with self.assertRaises(RecoveryError):
                    verify_bundle(bundle)

    def test_bad_manifest_and_extra_files_rejected(self):
        for change in ("format", "bundle_id", "artifacts", "snapshot", "extra"):
            with self.subTest(change=change):
                bundle = create_bundle(self.root, capture)
                if change == "extra":
                    (bundle / "unexpected").write_bytes(b"x")
                else:
                    manifest = json.loads((bundle / "manifest.json").read_text())
                    manifest[change] = None
                    (bundle / "manifest.json").write_text(json.dumps(manifest))
                with self.assertRaises(RecoveryError):
                    verify_bundle(bundle)

    def test_incomplete_and_symlink_packages_rejected(self):
        bundle = create_bundle(self.root, capture)
        linked = self.root / "link"
        linked.symlink_to(bundle, target_is_directory=True)
        with self.assertRaises(RecoveryError):
            verify_bundle(linked)
        (bundle / "database.dump").unlink()
        (bundle / "database.dump").symlink_to(self.root / "outside")
        with self.assertRaises(RecoveryError):
            verify_bundle(bundle)
        partial = self.root / ".partial-incomplete"
        partial.mkdir()
        with self.assertRaises(RecoveryError):
            verify_bundle(partial)

    def test_unsafe_archive_members_never_extracted(self):
        for name, kind in [
            ("../outside", tarfile.REGTYPE),
            ("/absolute", tarfile.REGTYPE),
            ("folder/audio.wav", tarfile.REGTYPE),
            ("x.tmp", tarfile.REGTYPE),
            (KEY, tarfile.SYMTYPE),
            (KEY, tarfile.LNKTYPE),
            (KEY, tarfile.FIFOTYPE),
            (KEY, tarfile.DIRTYPE),
        ]:
            with self.subTest(name=name, kind=kind):
                archive = self.root / "invalid.tar"
                write_tar(archive, [(name, PAYLOAD, kind)])
                with self.assertRaises(RecoveryError):
                    audio_inventory(archive)
                self.assertFalse((self.root / "outside").exists())

    def test_duplicate_and_oversized_audio_rejected(self):
        archive = self.root / "invalid.tar"
        write_tar(archive, [(KEY, PAYLOAD, tarfile.REGTYPE)] * 2)
        with self.assertRaises(RecoveryError):
            audio_inventory(archive)
        with tarfile.open(archive, "w") as handle:
            member = tarfile.TarInfo(KEY)
            member.size = MAX_AUDIO + 1
            handle.addfile(member)
        with self.assertRaises(RecoveryError):
            audio_inventory(archive)

    def test_missing_audio_and_wrong_size_never_published(self):
        def missing(path):
            metadata = capture(path)
            write_tar(path / "voice.tar", [("different.wav", PAYLOAD, tarfile.REGTYPE)])
            return metadata

        with self.assertRaises(RecoveryError):
            create_bundle(self.root, missing)
        self.assertFalse(list(self.root.glob("aulas-*")))
        with self.assertRaises(RecoveryError):
            check_references(SNAPSHOT, {KEY: {"size": 1}})

    def test_ready_without_key_rejected_pending_without_audio_allowed(self):
        for status in ("pending", "ready"):
            snapshot = {
                **SNAPSHOT,
                "audio": [{"key": None, "size": None, "status": status}],
            }
            if status == "ready":
                with self.assertRaises(RecoveryError):
                    check_references(snapshot, {})
            else:
                self.assertEqual(check_references(snapshot, {}), 0)

    def test_unreferenced_audio_preserved(self):
        def orphan(path):
            metadata = capture(path)
            write_tar(
                path / "voice.tar",
                [
                    (KEY, PAYLOAD, tarfile.REGTYPE),
                    ("orphan.wav", b"orphan", tarfile.REGTYPE),
                ],
            )
            return metadata

        manifest = verify_bundle(create_bundle(self.root, orphan))
        self.assertEqual(manifest["unreferenced_audio_count"], 1)
        self.assertIn("orphan.wav", manifest["audio_files"])

    def test_quarantine_bytes_and_journal_preserved_and_counted_separately(self):
        operation = "b" * 32
        entries = [
            (KEY, PAYLOAD, tarfile.REGTYPE),
            (f".quarantine/{operation}/audio", b"orphan voice", tarfile.REGTYPE),
            (f".quarantine/{operation}/record.json", b'{"version":1}', tarfile.REGTYPE),
            (f".quarantine/{operation}/restore.json", b'{"intent":"restore"}', tarfile.REGTYPE),
        ]

        def quarantine(path):
            metadata = capture(path)
            write_tar(path / "voice.tar", entries)
            return metadata

        bundle = create_bundle(self.root, quarantine)
        manifest = verify_bundle(bundle)
        self.assertEqual(manifest["quarantine_entry_count"], 3)
        self.assertEqual(manifest["unreferenced_audio_count"], 0)
        self.assertEqual(len(manifest["audio_files"]), 4)
        manifest["format"] = LEGACY_FORMAT
        (bundle / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(RecoveryError):
            verify_bundle(bundle)

    def test_legacy_backup_without_quarantine_remains_readable(self):
        bundle = create_bundle(self.root, capture)
        manifest = verify_bundle(bundle)
        manifest["format"] = LEGACY_FORMAT
        del manifest["quarantine_entry_count"]
        (bundle / "manifest.json").write_text(json.dumps(manifest))
        self.assertEqual(verify_bundle(bundle)["format"], LEGACY_FORMAT)

    def test_quarantine_path_allowlist_rejects_traversal_and_unexpected_files(self):
        for name in (
            ".quarantine/../audio",
            ".quarantine/" + "b" * 32 + "/../voice",
            ".quarantine/" + "b" * 32 + "/unexpected",
            ".quarantine/not-uuid/audio",
        ):
            with self.subTest(name=name):
                archive = self.root / "invalid.tar"
                write_tar(archive, [(name, PAYLOAD, tarfile.REGTYPE)])
                with self.assertRaises(RecoveryError):
                    audio_inventory(archive)

    def test_public_or_linked_output_directory_rejected(self):
        public = self.root / "public"
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        with self.assertRaises(RecoveryError):
            create_bundle(public, capture)
        linked = self.root / "linked"
        linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(RecoveryError):
            create_bundle(linked, capture)


class OperationalGuardsTests(unittest.TestCase):
    def test_upgrade_fixture_uses_previous_models_but_migrates_with_current_image(self):
        from ops.rollback_image import IMAGE as previous_image

        for empty in (True, False):
            intermediate = {"revision": [recovery.UPGRADE_FROM], "users": 0, "lessons": 0}
            with (
                self.subTest(empty=empty),
                patch.object(recovery, "check_target") as guard,
                patch.object(recovery, "lease", return_value=nullcontext()),
                patch.object(recovery, "quiet"),
                patch.object(recovery, "query", side_effect=[0] if empty else [1, intermediate]),
                patch.object(recovery, "voice"),
                patch.object(recovery, "audio_inventory", return_value={}),
                patch.object(recovery, "docker") as docker,
            ):
                recovery.upgrade_lab_prepare()
            guard.assert_called_once_with(recovery.UPGRADE_LAB)
            self.assertIn(recovery.HELPER, docker.call_args_list[0].args)
            if empty:
                self.assertEqual(docker.call_args_list[1].args[-4:],
                                 (recovery.HELPER, "alembic", "upgrade", recovery.UPGRADE_FROM))
            else:
                self.assertFalse(any("alembic" in c.args for c in docker.call_args_list))
            fixture = docker.call_args_list[-1].args
            self.assertEqual(fixture[-3:], (previous_image, "python", "/tools/recovery_fixture.py"))
            self.assertIn(f"{recovery.UPGRADE_PROJECT}_default", fixture)
            self.assertNotIn(recovery.HELPER, fixture)

    def test_malformed_container_inspection_is_refused(self):
        for value in (None, [], "private-value"):
            with (
                self.subTest(value=value),
                patch.object(
                    recovery, "docker", side_effect=[b"container-id", json.dumps([value]).encode()]
                ),
                self.assertRaises(RecoveryError) as error,
            ):
                recovery.container(recovery.PROJECT, "target-db")
            self.assertNotIn("private-value", str(error.exception))

    def test_invalid_voice_inventory_is_refused_before_accessing_destination(self):
        with (
            patch.object(recovery, "verify_bundle", return_value={"audio_files": None}),
            patch.object(recovery, "check_target") as target,
            self.assertRaises(RecoveryError),
        ):
            recovery.restore(Path("unused"), recovery.CONFIRM_TARGET)
        target.assert_not_called()

    def test_database_identity_and_mount_guards(self):
        for target in (recovery.RESTORE, recovery.DIALOGUE_LAB, recovery.DIALOGUE_RESTORE):
            with self.subTest(target=target):
                self._database_identity_and_mount_guards(target)

    def _database_identity_and_mount_guards(self, target):
        info = {
            "State": {"Running": True},
            "HostConfig": {"Privileged": False, "PortBindings": {}},
            "Config": {"Image": recovery.POSTGRES},
            "NetworkSettings": {"Networks": {f"{target.project}_default": {}}},
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": target.db_volume,
                    "Destination": "/var/lib/postgresql/data",
                },
                {
                    "Type": "bind",
                    "Source": str(
                        recovery.ROOT
                        / "infra"
                        / (
                            "test-db-init.sql"
                            if target == recovery.DIALOGUE_LAB
                            else "restore-db-init.sql"
                        )
                    ),
                    "Destination": "/docker-entrypoint-initdb.d/01-test.sql",
                    "RW": False,
                },
            ],
        }
        identity = {
            "database": target.database,
            "role": target.role,
            "marker": target.marker,
            "version": 160015,
            "super": False,
            "createdb": False,
            "createrole": False,
            "bypassrls": False,
            "replication": False,
        }
        changes = [
            ("HostConfig", "Privileged", True),
            ("HostConfig", "PortBindings", {"5432": []}),
            ("Config", "Image", "postgres:latest"),
            ("NetworkSettings", "Networks", {"prod_default": {}}),
            ("State", "Running", False),
        ]
        with (
            patch.object(recovery, "local_daemon"),
            patch.object(recovery, "volume"),
            patch.object(recovery, "container", return_value=info) as read,
            patch.object(recovery, "query", return_value=identity) as sql,
        ):
            self.assertEqual(recovery.check_target(target), info)
            for section, key, value in changes:
                changed = copy.deepcopy(info)
                changed[section][key] = value
                read.return_value = changed
                with self.subTest(section=section, key=key), self.assertRaises(RecoveryError):
                    recovery.check_target(target)
            for index, key, value in [
                (0, "Name", "aulas-ingles-pgdata-prod"),
                (1, "RW", True),
                (1, "Source", "/another/init.sql"),
                (1, "Destination", "/other.sql"),
            ]:
                changed = copy.deepcopy(info)
                changed["Mounts"][index][key] = value
                read.return_value = changed
                with self.subTest(mount=key), self.assertRaises(RecoveryError):
                    recovery.check_target(target)
            read.return_value = info
            for key, value in {
                "marker": "production",
                "database": "real",
                "role": "postgres",
                "version": 150015,
                "super": True,
                "createdb": True,
                "createrole": True,
                "bypassrls": True,
                "replication": True,
            }.items():
                sql.return_value = {**identity, key: value}
                with self.subTest(identity=key), self.assertRaises(RecoveryError):
                    recovery.check_target(target)

    def test_desktop_mount_alias_is_exact_and_only_on_macos(self):
        expected = Path("/Users/example/repo/infra/test-db-init.sql")
        with patch.object(recovery.sys, "platform", "darwin"):
            self.assertTrue(recovery.expected_bind_source(str(expected), expected))
            self.assertTrue(recovery.expected_bind_source(f"/host_mnt{expected}", expected))
            self.assertFalse(recovery.expected_bind_source(f"/other{expected}", expected))
            self.assertFalse(recovery.expected_bind_source(f"/host_mnt{expected}.other", expected))
        with patch.object(recovery.sys, "platform", "linux"):
            self.assertFalse(recovery.expected_bind_source(f"/host_mnt{expected}", expected))

    def test_actual_backup_command_failure_never_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []

            def broken_dump(*args, **kwargs):
                calls.append(args)
                kwargs["stdout"].write(b"truncated-dump")
                raise RecoveryError("pg_dump falhou")

            with (
                patch.object(recovery, "BACKUPS", root),
                patch.object(recovery, "local_daemon"),
                patch.object(recovery, "check_target", return_value={"Id": "lab-db"}),
                patch.object(recovery, "quiet"),
                patch.object(recovery, "lease", return_value=nullcontext()),
                patch.object(recovery, "query", return_value=SNAPSHOT),
                patch.object(recovery, "db_args", return_value=["exec", "lab-db", "pg_dump"]),
                patch.object(recovery, "docker", side_effect=broken_dump),
                self.assertRaises(RecoveryError),
            ):
                recovery.backup("lab")
            self.assertEqual(calls, [("exec", "lab-db", "pg_dump", "-Fc")])
            self.assertFalse(list(root.glob("aulas-*")))
            self.assertEqual(len(list(root.glob(".partial-*"))), 1)

    def test_success_with_dump_warning_is_not_approved(self):
        import subprocess

        result = subprocess.CompletedProcess([], 0, stdout=b"", stderr=b"private warning")
        with (
            patch.object(recovery.subprocess, "run", return_value=result),
            self.assertRaises(RecoveryError) as error,
        ):
            recovery.run(["pg_dump"], reject_stderr=True)
        self.assertNotIn("private", str(error.exception))

    def test_nonempty_voice_blocks_restore_before_database_write(self):
        def export(_target, _action, *, stdout):
            write_tar(Path(stdout.name))

        with (
            patch.object(recovery, "verify_bundle", return_value={"audio_files": {}}),
            patch.object(recovery, "check_target"),
            patch.object(recovery, "quiet"),
            patch.object(recovery, "lease", return_value=nullcontext()),
            patch.object(recovery, "query", return_value=0),
            patch.object(recovery, "voice", side_effect=export),
            patch.object(recovery, "docker") as command,
            self.assertRaisesRegex(RecoveryError, "voz não está vazio"),
        ):
            recovery.restore(Path("unused"), recovery.CONFIRM_TARGET)
        command.assert_not_called()

    def test_restore_lock_conflict_does_not_remove_existing_lock(self):
        with (
            patch.object(recovery, "docker", side_effect=RecoveryError("lock ocupado")) as cmd,
            self.assertRaises(RecoveryError),
            recovery.lease("restore"),
        ):
            self.fail("Lease existente deve bloquear")
        self.assertEqual(cmd.call_count, 1)
        self.assertEqual(cmd.call_args.args[0], "create")

    def test_lease_releases_only_its_exact_container_after_failure(self):
        with (
            patch.object(recovery, "docker", side_effect=[b"exact-id\n", b""]) as cmd,
            self.assertRaises(RecoveryError),
            recovery.lease("restore"),
        ):
            raise RecoveryError("falha de restore")
        self.assertEqual(cmd.call_args.args, ("rm", "exact-id"))

    def test_remote_docker_rejected_before_command(self):
        with (
            patch.dict("os.environ", {"DOCKER_HOST": "tcp://production:2375"}),
            patch.object(recovery, "docker") as command,
            self.assertRaises(RecoveryError),
        ):
            recovery.local_daemon()
        command.assert_not_called()

    def test_volume_ownership_marker_driver_and_redirection(self):
        valid = {
            "Name": recovery.RESTORE.voice_volume,
            "Driver": "local",
            "Scope": "local",
            "Options": None,
            "Labels": {
                "com.docker.compose.project": recovery.PROJECT,
                "org.aulas.environment": "disposable-recovery",
            },
        }
        recovery.validate_volume(valid, recovery.PROJECT, recovery.RESTORE.voice_volume, True)
        for change in (
            {"Name": "aulas-ingles-speaking-data-prod"},
            {"Driver": "nfs"},
            {"Scope": "global"},
            {"Options": {"type": "none", "o": "bind", "device": "/real-study"}},
            {"Labels": {}},
        ):
            with self.subTest(change=change), self.assertRaises(RecoveryError):
                recovery.validate_volume(
                    {**valid, **change},
                    recovery.PROJECT,
                    recovery.RESTORE.voice_volume,
                    True,
                )

    def test_running_production_api_blocks_backup(self):
        target = recovery.Target("aulas-ingles-prod", "db", "study", "app", "db", "voice", None)
        with (
            patch.object(recovery, "container", return_value={"State": {"Running": True}}),
            patch.object(recovery, "docker") as command,
            self.assertRaises(RecoveryError),
        ):
            recovery.quiet(target)
        command.assert_not_called()

    def test_active_voice_consumer_blocks_backup(self):
        with (
            patch.object(recovery, "docker", return_value=b"a-container"),
            patch.object(recovery, "query") as query,
            self.assertRaises(RecoveryError),
        ):
            recovery.quiet(recovery.LAB)
        query.assert_not_called()

    def test_other_database_client_blocks_backup(self):
        with (
            patch.object(recovery, "docker", return_value=b""),
            patch.object(recovery, "query", return_value=1),
            self.assertRaises(RecoveryError),
        ):
            recovery.quiet(recovery.LAB)

    def test_restore_requires_exact_confirmation_before_verification(self):
        with (
            patch.object(recovery, "verify_bundle") as verify,
            self.assertRaises(RecoveryError),
        ):
            recovery.restore(Path("missing"), "production")
        verify.assert_not_called()

    def test_restore_corrupt_bundle_does_not_access_docker(self):
        with (
            patch.object(recovery, "verify_bundle", side_effect=RecoveryError("invalid")),
            patch.object(recovery, "docker") as command,
            self.assertRaises(RecoveryError),
        ):
            recovery.restore(Path("missing"), recovery.CONFIRM_TARGET)
        command.assert_not_called()

    def test_nonempty_database_blocks_restore_without_cleanup(self):
        with (
            patch.object(recovery, "verify_bundle", return_value={"audio_files": {}}),
            patch.object(recovery, "check_target"),
            patch.object(recovery, "quiet"),
            patch.object(recovery, "lease", return_value=nullcontext()),
            patch.object(recovery, "query", return_value=1),
            patch.object(recovery, "docker") as command,
            self.assertRaisesRegex(RecoveryError, "PostgreSQL não está vazio"),
        ):
            recovery.restore(Path("unused"), recovery.CONFIRM_TARGET)
        command.assert_not_called()

    def test_voice_import_never_targets_source(self):
        from dataclasses import replace

        for target in (
            recovery.LAB, recovery.UPGRADE_LAB, recovery.DIALOGUE_LAB,
            replace(recovery.DIALOGUE_RESTORE, voice_volume="other-volume"),
            replace(recovery.DIALOGUE_RESTORE, project="aulas-ingles-prod"),
        ):
            with (
                self.subTest(target=target),
                patch.object(recovery, "docker") as command,
                self.assertRaises(RecoveryError),
            ):
                recovery.voice(target, "import")
            command.assert_not_called()

    def test_voice_import_accepts_only_registered_disposable_destinations(self):
        targets = (
            recovery.DESTINATIONS | recovery.UPGRADE_DESTINATIONS | recovery.DIALOGUE_DESTINATIONS
        )
        for target in targets.values():
            with self.subTest(target=target), patch.object(recovery, "docker") as command:
                recovery.voice(target, "import")
            args = command.call_args.args
            self.assertEqual(args[-1], "import")
            self.assertIn(f"type=volume,src={target.voice_volume},dst=/voice", args)
            self.assertEqual(args[args.index("--network") + 1], "none")
            self.assertIn("--read-only", args)

    def test_subprocess_error_does_not_leak_credentials(self):
        import subprocess

        with (
            patch.object(
                recovery.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(
                    1, ["sensitive-command"], stderr=b"secret password"
                ),
            ),
            self.assertRaises(RecoveryError) as result,
        ):
            recovery.run(["docker"])
        self.assertNotIn("secret", str(result.exception))
        self.assertNotIn("password", str(result.exception))


if __name__ == "__main__":
    unittest.main()
