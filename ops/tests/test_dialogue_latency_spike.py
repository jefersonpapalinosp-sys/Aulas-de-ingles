"""Harness do spike de latência: estatística, turnos sintéticos e provedor simulado."""

import io
import unittest
from contextlib import redirect_stdout

from ops import dialogue_latency_spike as spike


class SpikeTests(unittest.TestCase):
    def test_percentile_is_bounded_and_monotonic(self):
        values = [0.5, 0.1, 0.9, 0.3, 0.7]
        self.assertEqual(spike.percentile(values, 0.0), 0.1)
        self.assertEqual(spike.percentile(values, 1.0), 0.9)
        self.assertLessEqual(spike.percentile(values, 0.5), spike.percentile(values, 0.95))
        self.assertTrue(spike.percentile([], 0.5) != spike.percentile([], 0.5))  # NaN

    def test_synthetic_turns_cover_every_check_code_without_student_data(self):
        brief = spike.load_brief("voa-level-1", 31)
        turns = spike.synthetic_turns(brief, 8, seed=1)
        codes = {code for _, failed in turns for code in failed}
        self.assertEqual(codes, {"too_short", "target_terms_missing", "grammar_pattern_missing"})
        self.assertTrue(all(transcript for transcript, _ in turns))
        self.assertTrue(all("@" not in transcript for transcript, _ in turns))

    def test_mock_run_reports_all_turns_valid(self):
        brief = spike.load_brief("voa-level-1", 31)
        turns = spike.synthetic_turns(brief, 4, seed=2)
        provider = spike.mock_provider(seed=2)
        report = spike.run(provider, brief, turns)
        self.assertEqual(report["valid"], 4)
        self.assertEqual(report["invalid_output"], 0)
        self.assertEqual(report["transport_failures"], 0)
        self.assertGreater(report["latency_p95_s"], 0)
        self.assertEqual(report["prompt_version"], "dialogue-prompt-v1")

    def test_invalid_provider_output_is_counted_not_crashed(self):
        brief = spike.load_brief("voa-level-1", 31)
        turns = spike.synthetic_turns(brief, 2, seed=3)
        report = spike.run(lambda messages, schema: ("not json", None), brief, turns)
        self.assertEqual(report["invalid_output"], 2)
        self.assertEqual(report["valid"], 0)

    def test_cli_gateway_requires_url(self):
        with redirect_stdout(io.StringIO()):
            code = spike.main(["--provider", "gateway", "--turns", "1"])
        self.assertEqual(code, 2)

    def test_cli_mock_exits_zero(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = spike.main(["--provider", "mock", "--turns", "3", "--json"])
        self.assertEqual(code, 0)
        self.assertIn('"valid": 3', buffer.getvalue())
