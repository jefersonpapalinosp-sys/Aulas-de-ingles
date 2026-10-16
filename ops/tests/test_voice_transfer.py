"""Ensaia o transportador real em diretórios sintéticos, sem Docker/volumes do aluno."""

import importlib.util
import io
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ops import recovery_archive

spec = importlib.util.spec_from_file_location(
    "voice_transfer_tested", Path(__file__).parents[1] / "voice_transfer.py"
)
transfer = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"recovery_archive": recovery_archive}):
    spec.loader.exec_module(transfer)

KEY = "a" * 32 + ".wav"
OP = "b" * 32


class VoiceTransferTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_roundtrip_keeps_quarantine_and_interrupted_hardlink_as_regular_bytes(self):
        source = self.root / "source"
        source.mkdir()
        (source / KEY).write_bytes(b"synthetic audio")
        operation = source / ".quarantine" / OP
        operation.mkdir(parents=True)
        os.link(source / KEY, operation / "audio")
        (operation / "record.json").write_bytes(b'{"version":1}')
        (operation / "restore.json").write_bytes(b'{"intent":"restore"}')
        payload = io.BytesIO()
        with (
            patch.object(transfer, "ROOT", source),
            patch.object(transfer.sys, "stdout", SimpleNamespace(buffer=payload)),
        ):
            transfer.export_voice()
        with tarfile.open(fileobj=io.BytesIO(payload.getvalue())) as archive:
            self.assertEqual(len(archive.getmembers()), 4)
            self.assertTrue(all(item.isfile() for item in archive))
        destination = self.root / "destination"
        destination.mkdir()
        with (
            patch.object(transfer, "ROOT", destination),
            patch.object(
                transfer.sys,
                "stdin",
                SimpleNamespace(buffer=io.BytesIO(payload.getvalue())),
            ),
            patch.object(
                transfer.os, "chown"
            ),  # UID de container, não alterar dono do host.
        ):
            transfer.import_voice()
        for file in source.rglob("*"):
            if file.is_file():
                copied = destination / file.relative_to(source)
                self.assertEqual(copied.read_bytes(), file.read_bytes())
                self.assertEqual(copied.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            (destination / ".quarantine" / OP).stat().st_mode & 0o777, 0o700
        )

    def test_export_rejects_linked_quarantine_before_emitting_archive(self):
        (self.root / ".quarantine").symlink_to(self.root, target_is_directory=True)
        payload = io.BytesIO()
        with (
            patch.object(transfer, "ROOT", self.root),
            patch.object(transfer.sys, "stdout", SimpleNamespace(buffer=payload)),
            self.assertRaises(recovery_archive.RecoveryError),
        ):
            transfer.export_voice()
        self.assertEqual(payload.getvalue(), b"")

    def test_export_rejects_unexpected_quarantine_descendants(self):
        operation = self.root / ".quarantine" / OP
        operation.mkdir(parents=True)
        (operation / "unexpected").write_bytes(b"private")
        with (
            patch.object(transfer, "ROOT", self.root),
            self.assertRaises(recovery_archive.RecoveryError),
        ):
            transfer.export_voice()

    def test_empty_quarantine_is_not_mistaken_for_empty_restore_destination(self):
        quarantine = self.root / ".quarantine"
        quarantine.mkdir()
        for stage in ("parent", "operation"):
            with self.subTest(stage=stage):
                if stage == "operation":
                    (quarantine / OP).mkdir()
                with (
                    patch.object(transfer, "ROOT", self.root),
                    self.assertRaises(recovery_archive.RecoveryError),
                ):
                    transfer.export_voice()

    def test_bounded_directory_scan_refuses_excess_entries(self):
        for name in ("one", "two"):
            (self.root / name).write_bytes(b"x")
        with self.assertRaises(recovery_archive.RecoveryError):
            transfer.bounded_entries(self.root, limit=1)

    def test_import_rejects_traversal_without_creating_outside_file(self):
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w") as archive:
            member = tarfile.TarInfo(f".quarantine/{OP}/../../outside")
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        with (
            patch.object(transfer, "ROOT", self.root),
            patch.object(
                transfer.sys,
                "stdin",
                SimpleNamespace(buffer=io.BytesIO(payload.getvalue())),
            ),
            self.assertRaises(recovery_archive.RecoveryError),
        ):
            transfer.import_voice()
        self.assertEqual(list(self.root.iterdir()), [])
