"""Executa os blocos reais do workflow com probes sintéticos, sem rede."""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/operations.yml"


def bash_executable():
    if os.name == "nt":
        candidate = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Git/bin/bash.exe"
        if candidate.is_file():
            return str(candidate)
    return shutil.which("bash")


def step_script(name):
    text = WORKFLOW.read_text(encoding="utf-8")
    marker = f"      - name: {name}\n"
    block = text.split(marker, 1)[1].split("\n      - name:", 1)[0]
    script = block.split("        run: |\n", 1)[1]
    return "\n".join(line[10:] for line in script.splitlines() if line.startswith("          "))


@unittest.skipUnless(bash_executable(), "Bash necessário para o contrato do runner Linux.")
class OperationsWorkflowTests(unittest.TestCase):
    def run_step(
        self, name, *, origin="https://example.test", token="sentinel-private-token", code=0
    ):
        # A função substitui só o probe: o bloco do workflow é executado sem alterações.
        fake_probe = (
            'python3() { printf \'{"status":"synthetic"}\\n\'; return "$PROBE_TEST_EXIT"; }\n'
        )
        with tempfile.TemporaryDirectory(prefix="aulas-watch-test-") as folder:
            env = {
                **os.environ,
                "PUBLIC_ORIGIN": origin,
                "OPERATIONS_TOKEN": token,
                "GITHUB_OUTPUT": "outputs.txt",
                "GITHUB_STEP_SUMMARY": "summary.md",
                "PROBE_TEST_EXIT": str(code),
            }
            result = subprocess.run(
                [
                    bash_executable(),
                    "--noprofile",
                    "--norc",
                    "-e",
                    "-o",
                    "pipefail",
                    "-c",
                    fake_probe + step_script(name),
                ],
                cwd=folder,
                env=env,
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
            summary = Path(folder, "summary.md")
            outputs = Path(folder, "outputs.txt")
            return (
                result,
                summary.read_text(encoding="utf-8") if summary.exists() else "",
                outputs.read_text(encoding="utf-8") if outputs.exists() else "",
            )

    def test_disabled_deployment_is_explicit(self):
        result, _, outputs = self.run_step("decide o que está armado", origin="", token="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("probe=false", outputs)
        self.assertIn("metrics=false", outputs)

    def test_origin_without_token_fails_instead_of_partial_monitoring(self):
        result, _, outputs = self.run_step("decide o que está armado", token="")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("::error::", result.stdout)
        self.assertIn("metrics=false", outputs)

    def test_complete_configuration_arms_both_checks_without_leaking_token(self):
        result, _, outputs = self.run_step("decide o que está armado")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("probe=true", outputs)
        self.assertIn("metrics=true", outputs)
        self.assertNotIn("sentinel-private-token", result.stdout + result.stderr + outputs)

    def test_probes_preserve_success_failure_and_unavailable_with_summary(self):
        for step in (
            "probe externo de disponibilidade",
            "gate operacional (worker, fila, custo diário e mensal da assistência)",
        ):
            for code in (0, 1, 2):
                with self.subTest(step=step, code=code):
                    result, summary, _ = self.run_step(step, code=code)
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertIn('"status":"synthetic"', summary)
                    self.assertNotIn("sentinel-private-token", summary + result.stdout)

    def test_gate_runs_after_probe_failure_and_shell_is_explicit(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(text, r"defaults:\s+run:\s+shell: bash")
        gate = text.split("      - name: gate operacional", 1)[1]
        condition = re.search(r"^        if: (.+)$", gate, re.MULTILINE)
        self.assertIsNotNone(condition)
        self.assertIn("!cancelled()", condition.group(1))
        self.assertIn("steps.gate.outputs.metrics == 'true'", condition.group(1))
