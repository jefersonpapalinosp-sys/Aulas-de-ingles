"""Pré-carga das imagens-base do CI: duas origens, mesmo digest, espera limitada."""

import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops" / "ci_pull_bases.sh"
DOCKERFILES = (ROOT / "backend" / "Dockerfile.prod", ROOT / "frontend" / "Dockerfile.prod")
IMAGES = 4
MOCKS = r'''
ci_test_pulls=0
docker() {
  printf 'CALL'; printf ' %s' "$@"; printf '\n'
  if [ "$1" = tag ]; then
    [ "$CI_TEST_MODE" != tag_failure ]
    return
  fi
  ci_test_pulls=$((ci_test_pulls+1))
  case "$CI_TEST_MODE" in
    mirror|tag_failure) return 0 ;;
    official) [[ "$3" == docker.io/* ]] ;;
    transient) [ "$ci_test_pulls" -ge 3 ] ;;
    *) return 1 ;;
  esac
}
sleep() { printf 'WAIT %s\n' "$1"; }
source "$1"
'''


class BasePullTests(unittest.TestCase):
    def simulate(self, mode):
        return subprocess.run(
            ["bash", "-e", "-s", str(SCRIPT)],
            input=MOCKS,
            capture_output=True,
            text=True,
            env={**os.environ, "CI_TEST_MODE": mode},
            check=False,
            timeout=5,
        )

    def test_mirror_success_pulls_each_image_once_without_fallback(self):
        result = self.simulate("mirror")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("CALL pull"), IMAGES)
        self.assertEqual(result.stdout.count("CALL tag"), IMAGES)
        self.assertNotIn("docker.io/", result.stdout)
        self.assertNotIn("WAIT", result.stdout)

    def test_official_fallback_keeps_the_same_digest_per_image(self):
        result = self.simulate("official")
        self.assertEqual(result.returncode, 0, result.stderr)
        pulls = [line for line in result.stdout.splitlines() if line.startswith("CALL pull")]
        self.assertEqual(len(pulls), IMAGES * 2)
        for mirror, official in zip(pulls[0::2], pulls[1::2], strict=True):
            self.assertIn("public.ecr.aws/", mirror)
            self.assertIn("docker.io/", official)
            self.assertEqual(mirror.split("@sha256:")[1], official.split("@sha256:")[1])
        tags = [line for line in result.stdout.splitlines() if line.startswith("CALL tag")]
        self.assertEqual(len(tags), IMAGES)
        self.assertTrue(all("docker.io/library/" in tag for tag in tags))
        self.assertNotIn("WAIT", result.stdout)

    def test_transient_failure_waits_once_then_recovers(self):
        result = self.simulate("transient")
        self.assertEqual(result.returncode, 0, result.stderr)
        # Primeira imagem: espelho e oficial falham, espera, terceira tentativa passa.
        self.assertEqual(result.stdout.count("CALL pull"), 3 + (IMAGES - 1))
        self.assertEqual(result.stdout.count("WAIT"), 1)
        self.assertIn("WAIT 45", result.stdout)

    def test_persistent_failure_is_bounded_and_never_tags(self):
        result = self.simulate("unavailable")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout.count("CALL pull"), 8)
        waits = [line for line in result.stdout.splitlines() if line.startswith("WAIT")]
        self.assertEqual(waits, ["WAIT 45", "WAIT 90", "WAIT 135"])
        self.assertNotIn("CALL tag", result.stdout)
        self.assertIn("::error::", result.stdout)

    def test_tag_failure_does_not_report_success(self):
        result = self.simulate("tag_failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("verificada por digest", result.stdout)

    def test_shell_syntax_and_aliases_match_the_dockerfiles(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        script = SCRIPT.read_text()
        froms = set()
        for dockerfile in DOCKERFILES:
            froms.update(re.findall(r"^FROM\s+(public\.ecr\.aws/\S+)", dockerfile.read_text(), re.M))
        self.assertTrue(froms)
        for reference in froms:
            self.assertIn(f'"{reference}|', script, f"{reference} sem pré-carga em {SCRIPT.name}")
        # Base do commit fixo que ops/rollback_image.py reconstrói no laboratório DB-42.
        self.assertIn('"public.ecr.aws/docker/library/python:3.12-slim|', script)
        digests = re.findall(r"\|sha256:([0-9a-f]+)\"", script)
        self.assertEqual(len(digests), IMAGES)
        self.assertTrue(all(len(digest) == 64 for digest in digests))
