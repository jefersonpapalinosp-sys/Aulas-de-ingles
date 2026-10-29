"""Criptografia e cópia com arquivos sintéticos e processos simulados, sem chaves reais."""

import hashlib
import io
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ops import public_backup as backup
from ops.recovery_archive import RecoveryError

RECIPIENT = "age1" + "q" * 58
SEALED = b"synthetic-encrypted-payload"


class PublicBackupCryptoTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle = self.root / "synthetic-bundle"
        self.bundle.mkdir()
        self.output = self.root / "encrypted"
        self.target = self.output / f"{self.bundle.name}.tar.age"

    def pipeline(self, *, tar_code: int = 0, age_code: int = 0):
        process = MagicMock()
        process.__enter__.return_value = process
        process.stdout = io.BytesIO(b"synthetic-tar")
        process.returncode = tar_code

        def age(command, **kwargs):
            kwargs["stdout"].write(SEALED)
            return subprocess.CompletedProcess(command, age_code)

        return process, age

    def test_success_requires_both_processes_and_returns_checksum(self) -> None:
        tar, age = self.pipeline()
        with (
            patch.object(backup.shutil, "which", return_value="age"),
            patch.object(backup.subprocess, "Popen", return_value=tar),
            patch.object(backup.subprocess, "run", side_effect=age) as run,
        ):
            result = backup.encrypt(self.bundle, RECIPIENT, self.output)
        self.assertEqual(
            result,
            {
                "path": str(self.target),
                "recipient": RECIPIENT,
                "size": len(SEALED),
                "sha256": hashlib.sha256(SEALED).hexdigest(),
            },
        )
        self.assertEqual(self.target.read_bytes(), SEALED)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        self.assertEqual(run.call_args.args[0], ["age", "-r", RECIPIENT])
        tar.wait.assert_called_once_with(timeout=120)
        self.assertTrue(tar.stdout.closed)

    def test_failure_of_either_process_removes_only_generated_output(self) -> None:
        for tar_code, age_code in ((1, 0), (0, 1)):
            tar, age = self.pipeline(tar_code=tar_code, age_code=age_code)
            with (
                self.subTest(tar=tar_code, age=age_code),
                patch.object(backup.shutil, "which", return_value="age"),
                patch.object(backup.subprocess, "Popen", return_value=tar),
                patch.object(backup.subprocess, "run", side_effect=age),
                self.assertRaises(RecoveryError),
            ):
                backup.encrypt(self.bundle, RECIPIENT, self.output)
            self.assertFalse(self.target.exists())
            self.assertTrue(self.bundle.is_dir())

    def test_timeout_does_not_leave_output_or_reflect_subprocess_details(self) -> None:
        tar, _ = self.pipeline()
        with (
            patch.object(backup.shutil, "which", return_value="age"),
            patch.object(backup.subprocess, "Popen", return_value=tar),
            patch.object(
                backup.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(
                    "private-command",
                    900,
                    stderr=b"private-error",
                ),
            ),
            self.assertRaises(RecoveryError) as error,
        ):
            backup.encrypt(self.bundle, RECIPIENT, self.output)
        self.assertFalse(self.target.exists())
        self.assertNotIn("private", str(error.exception))

    def test_file_created_by_another_process_is_not_deleted_on_exclusive_open_failure(self) -> None:
        original = Path.open

        def racing_open(path, *args, **kwargs):
            if path == self.target and args == ("xb",):
                with original(path, "wb") as stream:
                    stream.write(b"another-process")
            return original(path, *args, **kwargs)

        with (
            patch.object(backup.shutil, "which", return_value="age"),
            patch.object(Path, "open", racing_open),
            patch.object(backup.subprocess, "Popen") as process,
            self.assertRaises(RecoveryError),
        ):
            backup.encrypt(self.bundle, RECIPIENT, self.output)
        self.assertEqual(self.target.read_bytes(), b"another-process")
        process.assert_not_called()

    def test_existing_output_is_preserved_before_starting_processes(self) -> None:
        self.output.mkdir(mode=0o700)
        self.target.write_bytes(b"existing")
        with (
            patch.object(backup.shutil, "which", return_value="age"),
            patch.object(backup.subprocess, "Popen") as process,
            self.assertRaises(RecoveryError),
        ):
            backup.encrypt(self.bundle, RECIPIENT, self.output)
        self.assertEqual(self.target.read_bytes(), b"existing")
        process.assert_not_called()

    def test_external_copy_verifies_bytes_and_refuses_overwrite(self) -> None:
        source = self.root / "synthetic.tar.age"
        source.write_bytes(SEALED)
        destination = self.root / "external-synthetic"
        destination.mkdir()
        result = backup.copy_external(source, destination)
        target = Path(result["path"])
        self.assertEqual(target.read_bytes(), SEALED)
        self.assertEqual(result["sha256"], hashlib.sha256(SEALED).hexdigest())
        source.write_bytes(b"changed")
        with self.assertRaises(RecoveryError):
            backup.copy_external(source, destination)
        self.assertEqual(target.read_bytes(), SEALED)

    @unittest.skipUnless(shutil.which("tar"), "tar necessário para validar o empacotamento real")
    def test_real_tar_contains_only_bundle_files_without_appledouble(self) -> None:
        files = {"database.dump": b"synthetic", "voice.tar": b"voice", "manifest.json": b"{}"}
        for name, payload in files.items():
            (self.bundle / name).write_bytes(payload)

        def copy_stream(command, **kwargs):
            # Substitui apenas age para inspecionar o tar real; não afirma testar criptografia.
            shutil.copyfileobj(kwargs["stdin"], kwargs["stdout"])
            return subprocess.CompletedProcess(command, 0)

        with (
            patch.object(backup.shutil, "which", return_value="synthetic-age"),
            patch.object(backup.subprocess, "run", side_effect=copy_stream),
        ):
            result = backup.encrypt(self.bundle, RECIPIENT, self.output)
        with tarfile.open(result["path"], mode="r:") as archive:
            names = {member.name for member in archive if member.isfile()}
            self.assertEqual(names, {f"{self.bundle.name}/{name}" for name in files})
            for name, payload in files.items():
                stream = archive.extractfile(f"{self.bundle.name}/{name}")
                self.assertIsNotNone(stream)
                self.assertEqual(stream.read(), payload)

    def test_external_copy_does_not_overwrite_concurrent_destination(self) -> None:
        source = self.root / "synthetic.tar.age"
        source.write_bytes(SEALED)
        destination = self.root / "external-synthetic"
        destination.mkdir()
        target = destination / source.name
        original = Path.open

        def racing_open(path, *args, **kwargs):
            if path == target and args == ("xb",):
                with original(path, "wb") as stream:
                    stream.write(b"another-process")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", racing_open), self.assertRaises(RecoveryError):
            backup.copy_external(source, destination)
        self.assertEqual(target.read_bytes(), b"another-process")
        self.assertEqual(source.read_bytes(), SEALED)

    def test_external_copy_refuses_symlink_source_before_creating_destination(self) -> None:
        private = self.root / "private-file"
        private.write_bytes(b"private-data")
        source = self.root / "linked.tar.age"
        source.symlink_to(private)
        destination = self.root / "external-synthetic"
        destination.mkdir()
        with self.assertRaises(RecoveryError):
            backup.copy_external(source, destination)
        self.assertEqual(list(destination.iterdir()), [])
