"""Falhas de formato e publicação, somente em diretórios temporários sintéticos."""

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops import recovery_archive as archive


def capture(path: Path) -> dict[str, object]:
    (path / "database.dump").write_bytes(b"synthetic-dump")
    with tarfile.open(path / "voice.tar", "w") as handle:
        member = tarfile.TarInfo("synthetic.wav")
        member.size = 5
        handle.addfile(member, io.BytesIO(b"voice"))
    return {"snapshot": {"revision": ["synthetic"], "counts": {}, "audio": []}}


class RecoveryArchiveFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_invalid_manifest_shapes_are_operational_errors_without_payload(self) -> None:
        bundle = archive.create_bundle(self.root, capture)
        for value in (None, [], "private-content", {}, {"artifacts": []}):
            with self.subTest(value=value):
                (bundle / "manifest.json").write_text(json.dumps(value))
                with self.assertRaises(archive.RecoveryError) as error:
                    archive.verify_bundle(bundle)
                self.assertNotIn("private-content", str(error.exception))

    def test_manifest_missing_keys_and_invalid_json_are_sanitized(self) -> None:
        bundle = archive.create_bundle(self.root, capture)
        for content in ('{"artifacts":{}}', '{"private-content":'):
            (bundle / "manifest.json").write_text(content)
            with self.assertRaises(archive.RecoveryError) as error:
                archive.verify_bundle(bundle)
            self.assertNotIn("private-content", str(error.exception))

    def test_invalid_snapshot_shapes_and_duplicate_references_are_refused(self) -> None:
        info = {"size": 5, "sha256": "synthetic"}
        reference = {"key": "synthetic.wav", "size": 5, "status": "ready"}
        snapshots = [
            None,
            {"revision": []},
            {"revision": ["v"], "counts": [], "audio": []},
            {"revision": ["v"], "counts": {}, "audio": {}},
            {"revision": ["v"], "counts": {}, "audio": [None]},
            {"revision": ["v"], "counts": {}, "audio": [reference, reference]},
        ]
        for snapshot in snapshots:
            with self.subTest(snapshot=snapshot), self.assertRaises(archive.RecoveryError):
                archive.check_references(snapshot, {"synthetic.wav": info})

    def test_invalid_tar_and_truncated_payload_are_never_extracted(self) -> None:
        path = self.root / "voice.tar"
        member = tarfile.TarInfo("synthetic.wav")
        member.size = 4096
        for content in (b"not-a-tar", member.tobuf() + b"short"):
            path.write_bytes(content)
            with self.assertRaises(archive.RecoveryError):
                archive.audio_inventory(path)
            self.assertFalse((self.root / "synthetic.wav").exists())

    def test_inventory_enforces_count_and_total_size(self) -> None:
        capture(self.root)
        for limit, value in (("MAX_FILES", 0), ("MAX_TOTAL", 4)):
            with patch.object(archive, limit, value), self.assertRaises(archive.RecoveryError):
                archive.audio_inventory(self.root / "voice.tar")

    def test_linked_manifest_is_refused_without_following_it(self) -> None:
        bundle = archive.create_bundle(self.root, capture)
        outside = self.root / "private.json"
        outside.write_text("private-content")
        manifest = bundle / "manifest.json"
        manifest.unlink()
        manifest.symlink_to(outside)
        with self.assertRaises(archive.RecoveryError):
            archive.verify_bundle(bundle)
        self.assertEqual(outside.read_text(), "private-content")

    def test_durability_failure_preserves_partial_without_publishing(self) -> None:
        with (
            patch.object(archive.os, "fsync", side_effect=OSError("synthetic-disk-error")),
            self.assertRaises(OSError),
        ):
            archive.create_bundle(self.root, capture)
        self.assertEqual(list(self.root.glob("aulas-*")), [])
        partials = list(self.root.glob(".partial-*"))
        self.assertEqual(len(partials), 1)
        self.assertEqual(partials[0].stat().st_mode & 0o777, 0o700)
        self.assertEqual((partials[0] / "database.dump").read_bytes(), b"synthetic-dump")
        with self.assertRaises(archive.RecoveryError):
            archive.verify_bundle(partials[0])

    def test_write_json_never_overwrites_an_existing_receipt(self) -> None:
        path = self.root / "receipt.json"
        archive.write_json(path, {"verified": True})
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            archive.write_json(path, {"verified": False})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
