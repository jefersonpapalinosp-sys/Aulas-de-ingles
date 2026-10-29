"""Bootstrap somente sobre arquivos sintéticos temporários; nunca altera o seed real."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from ops import bootstrap_editorial_keys as bootstrap


class BootstrapEditorialTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "seed").mkdir()
        self.courses = [
            {
                "slug": "synthetic",
                "units": [
                    {
                        "slug": "unit",
                        "review": {"questions": [{"position": 1, "text": "Synthetic"}]},
                    }
                ],
            }
        ]
        self.lessons = [
            {
                "course_slug": "synthetic",
                "number": 1,
                "exercises": [{"position": 1}],
                "writing_prompts": [{"position": 1}],
                "vocab": [{"term": "sample"}],
                "media": [{"position": 1, "cues": [{"position": 1}]}],
            }
        ]
        self.paths = [self.root / "seed/courses.json", self.root / "seed/lessons.json"]
        self.save()

    def save(self):
        for path, value in zip(self.paths, (self.courses, self.lessons), strict=True):
            path.write_text(json.dumps(value))

    def run_bootstrap(self, apply=False):
        output = io.StringIO()
        with (
            patch.object(bootstrap, "ROOT", self.root),
            patch.object(bootstrap.sys, "argv", ["bootstrap", *(["--apply"] if apply else [])]),
            redirect_stdout(output),
        ):
            bootstrap.main()
        return json.loads(output.getvalue())

    def test_dry_run_preserves_bytes_and_reports_all_six_entity_types(self):
        before = [path.read_bytes() for path in self.paths]
        report = self.run_bootstrap()
        self.assertFalse(report["applied"])
        self.assertEqual(len(report["counts"]), 6)
        self.assertEqual(set(report["counts"].values()), {1})
        self.assertEqual(len(report["content_sha256_excluding_keys"]), 64)
        self.assertEqual([path.read_bytes() for path in self.paths], before)

    def test_apply_adds_keys_to_original_nested_records_only(self):
        dry = self.run_bootstrap()
        applied = self.run_bootstrap(apply=True)
        self.assertEqual(
            dry["content_sha256_excluding_keys"], applied["content_sha256_excluding_keys"]
        )
        documents = [json.loads(path.read_text()) for path in self.paths]
        keys = []
        for table, item, location in bootstrap.records(*documents):
            key = item.pop("editorial_key")
            self.assertEqual(UUID(key).version, 5)
            self.assertEqual(key, bootstrap.bootstrap_key(table, *location))
            keys.append(key)
        self.assertEqual(len(set(keys)), 6)
        self.assertEqual(documents, [self.courses, self.lessons])

    def test_reapplying_refuses_without_overwriting_any_file(self):
        self.run_bootstrap(apply=True)
        before = [path.read_bytes() for path in self.paths]
        with self.assertRaisesRegex(SystemExit, "already contains keys"):
            self.run_bootstrap(apply=True)
        self.assertEqual([path.read_bytes() for path in self.paths], before)

    def test_duplicate_coordinate_refuses_before_any_write(self):
        self.lessons[0]["exercises"].append({"position": 1, "text": "different"})
        self.save()
        before = [path.read_bytes() for path in self.paths]
        with self.assertRaisesRegex(SystemExit, "Duplicate baseline coordinate"):
            self.run_bootstrap(apply=True)
        self.assertEqual([path.read_bytes() for path in self.paths], before)

    def test_zero_based_positions_keep_their_original_identity(self):
        self.lessons[0]["exercises"][0]["position"] = 0
        self.lessons[0]["media"][0]["cues"][0]["position"] = 0
        self.save()
        self.run_bootstrap(apply=True)
        lesson = json.loads(self.paths[1].read_text())[0]
        self.assertEqual(
            lesson["exercises"][0]["editorial_key"],
            bootstrap.bootstrap_key("exercise", "synthetic", 1, 0),
        )
        self.assertEqual(
            lesson["media"][0]["cues"][0]["editorial_key"],
            bootstrap.bootstrap_key("transcript_cue", "synthetic", 1, 1, 0),
        )

    def test_malformed_nested_seed_refuses_before_writing(self):
        original = deepcopy(self.lessons)
        for value in (None, {}, [None], [{"position": True}], [{"position": []}]):
            self.lessons = deepcopy(original)
            self.lessons[0]["exercises"] = value
            self.save()
            before = [path.read_bytes() for path in self.paths]
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_bootstrap(apply=True)
            self.assertEqual([path.read_bytes() for path in self.paths], before)
