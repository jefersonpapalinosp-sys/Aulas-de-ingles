import os
import subprocess
import unittest
from pathlib import Path

from ops.recovery import POSTGRES

SCRIPT = Path(__file__).resolve().parents[1] / "ci_pull_postgres.sh"
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


class PostgresPullTests(unittest.TestCase):
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

    def test_mirror_success_needs_no_fallback_or_wait(self):
        result = self.simulate("mirror")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("CALL pull"), 1)
        self.assertNotIn("docker.io/", result.stdout)
        self.assertNotIn("WAIT", result.stdout)

    def test_official_fallback_uses_exactly_the_same_digest(self):
        result = self.simulate("official")
        self.assertEqual(result.returncode, 0, result.stderr)
        pulls = [line for line in result.stdout.splitlines() if line.startswith("CALL pull")]
        self.assertEqual(len(pulls), 2)
        self.assertEqual(pulls[0].split("@sha256:")[1], pulls[1].split("@sha256:")[1])
        self.assertIn("CALL tag docker.io/library/postgres@sha256:", result.stdout)
        self.assertIn(POSTGRES, result.stdout)
        self.assertNotIn("WAIT", result.stdout)

    def test_transient_failure_waits_before_another_round(self):
        result = self.simulate("transient")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("CALL pull"), 3)
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
        self.assertNotIn("PostgreSQL verificado", result.stdout)

    def test_shell_syntax_and_operational_image_alias(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        self.assertIn(f'ci_postgres_image="{POSTGRES}"', SCRIPT.read_text())
