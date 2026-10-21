"""Harness do spike de latência: estatística, turnos sintéticos, provedores simulados e parsers."""

import io
import json
import os
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from ops import dialogue_latency_spike as spike


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


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

    def test_synthetic_wav_is_valid_mono_16khz(self):
        data = spike.synthetic_wav(2.0, seed=3)
        with wave.open(io.BytesIO(data), "rb") as archive:
            self.assertEqual(archive.getnchannels(), 1)
            self.assertEqual(archive.getframerate(), 16_000)
            self.assertEqual(archive.getsampwidth(), 2)
            self.assertEqual(archive.getnframes(), 32_000)

    def test_mock_run_reports_all_turns_valid(self):
        brief = spike.load_brief("voa-level-1", 31)
        turns = spike.synthetic_turns(brief, 4, seed=2)
        report = spike.run(spike.mock_provider(seed=2), brief, turns)
        self.assertEqual(report["valid"], 4)
        self.assertEqual(report["invalid_output"], 0)
        self.assertEqual(report["transport_failures"], 0)
        self.assertGreater(report["llm"]["p95_s"], 0)
        self.assertIsNone(report["stt"])
        self.assertTrue(report["p95_within_adr_budget"])
        self.assertEqual(report["prompt_version"], "dialogue-prompt-v1")

    def test_run_with_stt_accounts_both_latencies_and_neurons(self):
        brief = spike.load_brief("voa-level-1", 31)
        turns = spike.synthetic_turns(brief, 3, seed=5)
        calls = []

        def provider(messages, schema):
            return (
                {"partner_text": "Nice.", "hints": [], "confidence": 0.7},
                None,
                {"neurons": 4.0, "prompt_tokens": 600, "completion_tokens": 50},
            )

        def stt(audio):
            calls.append(len(audio))
            return "Thank you.", {"neurons": 6.0}

        report = spike.run(provider, brief, turns, stt=stt, audio=b"wav")
        self.assertEqual(calls, [3, 3, 3])
        self.assertEqual(report["valid"], 3)
        self.assertIsNotNone(report["stt"])
        self.assertGreaterEqual(report["total"]["p95_s"], report["llm"]["p95_s"])
        self.assertEqual(report["neurons_total"], 30.0)
        self.assertEqual(report["neurons_per_turn"], 10.0)
        self.assertEqual(report["free_turns_per_day_estimate"], 1000)
        self.assertEqual(report["prompt_tokens"], 1800)
        self.assertEqual(report["completion_tokens"], 150)

    def test_invalid_provider_output_is_counted_not_crashed(self):
        brief = spike.load_brief("voa-level-1", 31)
        turns = spike.synthetic_turns(brief, 2, seed=3)
        report = spike.run(lambda messages, schema: ("not json", None, None), brief, turns)
        self.assertEqual(report["invalid_output"], 2)
        self.assertEqual(report["valid"], 0)

    def test_cloudflare_chat_parser_accepts_object_and_string_json(self):
        turn = {"partner_text": "Hi!", "hints": [], "confidence": 0.5}
        usage = {"neurons": 4.875, "prompt_tokens": 608, "completion_tokens": 68}
        raw, parsed_usage = spike.parse_cloudflare_chat(
            {"success": True, "result": {"response": turn, "usage": usage}}
        )
        self.assertEqual(raw, turn)
        self.assertEqual(parsed_usage, usage)
        raw, _ = spike.parse_cloudflare_chat({"result": {"response": json.dumps(turn)}})
        self.assertEqual(raw, turn)
        raw, parsed_usage = spike.parse_cloudflare_chat({"errors": [{"code": 5025}]})
        self.assertIsNone(parsed_usage)

    def test_cloudflare_provider_and_stt_send_bearer_and_schema_without_network(self):
        seen = []

        def fake_urlopen(request, timeout):
            headers = dict(request.header_items())
            binary = headers.get("Content-type") == "application/octet-stream"
            seen.append(
                (request.full_url, headers, request.data if binary else json.loads(request.data))
            )
            if "whisper" in request.full_url:
                return FakeResponse({"result": {"text": "Thank you.", "usage": {"neurons": 6.2}}})
            return FakeResponse(
                {
                    "result": {
                        "response": {"partner_text": "Hi!", "hints": [], "confidence": 0.5},
                        "usage": {"neurons": 4.0},
                    }
                }
            )

        with patch.object(spike.urllib.request, "urlopen", fake_urlopen):
            provider = spike.cloudflare_provider("acc", "tok", spike.CLOUDFLARE_CHAT_MODEL, 5)
            raw, cost, usage = provider([{"role": "user", "content": "x"}], {"type": "object"})
            stt = spike.cloudflare_stt("acc", "tok", spike.CLOUDFLARE_STT_MODEL, 5)
            text, stt_usage = stt(b"RIFF")
            base_stt = spike.cloudflare_stt("acc", "tok", "@cf/openai/whisper", 5)
            base_text, _ = base_stt(b"RIFF")
        self.assertEqual(base_text, "Thank you.")
        _, base_headers, base_body = seen[2]
        self.assertEqual(base_headers.get("Content-type"), "application/octet-stream")
        self.assertEqual(base_body, b"RIFF")
        self.assertEqual(raw["partner_text"], "Hi!")
        self.assertIsNone(cost)
        self.assertEqual(usage["neurons"], 4.0)
        self.assertEqual(text, "Thank you.")
        self.assertEqual(stt_usage["neurons"], 6.2)
        chat_url, chat_headers, chat_body = seen[0]
        self.assertIn("/accounts/acc/ai/run/@cf/meta/llama-3.1-8b-instruct", chat_url)
        self.assertEqual(chat_headers.get("Authorization"), "Bearer tok")
        self.assertEqual(chat_body["response_format"]["type"], "json_schema")
        self.assertEqual(chat_body["temperature"], 0)
        _, _, stt_body = seen[1]
        self.assertEqual(stt_body["audio"], "UklGRg==")

    def test_cli_gateway_requires_url(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = spike.main(["--provider", "gateway", "--turns", "1"])
        self.assertEqual(code, 2)

    def test_cli_cloudflare_requires_account_and_token_without_printing_them(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLOUDFLARE_")}
        errors = io.StringIO()
        with patch.dict(os.environ, env, clear=True), redirect_stderr(errors):
            code = spike.main(["--provider", "cloudflare", "--turns", "1"])
        self.assertEqual(code, 2)
        self.assertIn("CLOUDFLARE_ACCOUNT_ID", errors.getvalue())

    def test_cli_mock_with_mock_stt_exits_zero(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = spike.main(["--provider", "mock", "--stt", "mock", "--turns", "3", "--json"])
        self.assertEqual(code, 0)
        report = json.loads(buffer.getvalue())
        self.assertEqual(report["valid"], 3)
        self.assertEqual(report["stt_provider"], "mock")
        self.assertIsNotNone(report["stt"])
