"""Recibos e ciclo de vida dos smokes de alinhamento; todos os comandos são simulados."""

import io
import json
import tempfile
import unittest
from contextlib import ExitStack, contextmanager, nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ops import assist_alignment as assist
from ops import concurrency_rollout, dev_alignment, recovery
from ops import sprint39_rollout as rollout
from ops.recovery_archive import RecoveryError

GOOD_HTTP = {
    "verified": True, "mode": "http-clone", "checks": 11,
    "synthetic_user_remaining": 0, "provider_calls": 0,
}


class AlignmentSmokeProcessTests(unittest.TestCase):
    @contextmanager
    def fixture(self, variant, *, payload=None, failures=0, drift=False):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            script = root / "smoke.py"
            script.write_text("# synthetic smoke script\n")
            info = {"size": 1, "sha256": "a" * 64}
            snapshot = {"revision": [assist.BASE], "counts": {}, "audio": []}
            manifest = {
                "source": {"kind": "dev", "project": "aulas-ingles"},
                "snapshot": snapshot, "bundle_id": "synthetic", "audio_files": {},
            }
            receipt = {
                "verified": True, "revision": assist.HEAD,
                "target": recovery.CONFIRM_ASSIST_CHECK,
                "manifest": info, "tools_image": "sha256:synthetic",
            }
            proof = {"manifest": info, "tools_image": "sha256:synthetic", "tables": {}}
            written = stack.enter_context(patch.object(assist, "write_json"))
            stack.enter_context(patch.object(recovery, "BACKUPS", root))
            stack.enter_context(patch.object(assist, "SMOKE_SCRIPT", script))
            stack.enter_context(patch.object(rollout, "SMOKE", script))
            stack.enter_context(patch.object(assist, "file_info", return_value=info))
            stack.enter_context(patch.object(assist, "verify_bundle", return_value=manifest))
            stack.enter_context(patch.object(
                dev_alignment, "image_id", return_value="sha256:synthetic"
            ))
            stack.enter_context(patch.object(dev_alignment, "verify_voice"))
            stack.enter_context(patch.object(assist, "verify_backfill"))
            stack.enter_context(patch.object(
                concurrency_rollout, "private_json", side_effect=[receipt, proof]
            ))
            stack.enter_context(patch.object(recovery, "check_target"))
            stack.enter_context(patch.object(recovery, "quiet"))
            stack.enter_context(patch.object(recovery, "lease", return_value=nullcontext()))
            stack.enter_context(patch.object(
                recovery, "query", return_value={**snapshot, "revision": [assist.HEAD]}
            ))
            stack.enter_context(patch.object(
                assist, "fingerprints", side_effect=[{}, {"changed": {}} if drift else {}]
            ))
            stack.enter_context(patch.object(assist.time, "sleep"))
            attempts = 0

            def docker(*args, **kwargs):
                nonlocal attempts
                if args[0] == "run":
                    self.assertIn(f"{recovery.PROJECT}_default", args)
                    self.assertIn("--read-only", args)
                    self.assertNotIn("--mount", args)
                    self.assertNotIn("-p", args)
                    self.assertIn("sha256:synthetic", args)
                    return b"synthetic-container\n"
                if args[0] == "exec" and "-c" in args:
                    attempts += 1
                    if attempts <= failures:
                        raise RecoveryError("Synthetic readiness failure")
                    return b""
                if args[0] == "exec":
                    self.assertEqual(kwargs["stdin"].read(), script.read_bytes())
                    return json.dumps(GOOD_HTTP if payload is None else payload).encode()
                self.assertIn(args[0], ("stop", "rm"))
                self.assertEqual(args[1], "synthetic-container")
                return b""

            command = stack.enter_context(patch.object(recovery, "docker", side_effect=docker))
            output = io.StringIO()
            stack.enter_context(redirect_stdout(output))

            def run():
                if variant == "assist":
                    return assist.smoke_clone(root)
                return rollout.smoke_clone(recovery.DEV39_CHECK, "dev", "sha256:synthetic")

            yield run, command, written, output

    def assert_cleanup(self, command):
        self.assertEqual(
            [call.args for call in command.call_args_list[-2:]],
            [("stop", "synthetic-container"), ("rm", "synthetic-container")],
        )

    def test_smoke_success_binds_payload_and_stops_only_its_container(self):
        for variant in ("assist", "sprint39"):
            with self.subTest(variant=variant), self.fixture(variant) as (run, command, write, _):
                result = run()
                self.assert_cleanup(command)
                if variant == "assist":
                    write.assert_called_once()
                    self.assertEqual(write.call_args.args[1]["http"], GOOD_HTTP)
                    self.assertIn("smoke_script", write.call_args.args[1])
                else:
                    self.assertEqual(result, GOOD_HTTP)

    def test_readiness_retries_before_running_smoke(self):
        for variant in ("assist", "sprint39"):
            with self.fixture(variant, failures=2) as (run, command, _, _):
                run()
                probes = [call for call in command.call_args_list if "-c" in call.args]
                self.assertEqual(len(probes), 3)
                self.assert_cleanup(command)

    def test_readiness_exhaustion_cleans_up_without_success(self):
        for variant in ("assist", "sprint39"):
            with self.fixture(variant, failures=20) as (run, command, write, output):
                with self.assertRaises(RecoveryError):
                    run()
                self.assertEqual(sum("-c" in call.args for call in command.call_args_list), 20)
                self.assert_cleanup(command)
                write.assert_not_called()
                self.assertEqual(output.getvalue(), "")

    def test_bad_http_evidence_is_refused_and_cleaned_up(self):
        for variant in ("assist", "sprint39"):
            for payload in (
                [], "private-value", {**GOOD_HTTP, "verified": 1},
                {**GOOD_HTTP, "provider_calls": False}, {**GOOD_HTTP, "checks": 11.0},
                {**GOOD_HTTP, "synthetic_user_remaining": 1}, {**GOOD_HTTP, "provider_calls": 1},
            ):
                with (
                    self.subTest(variant=variant, payload=payload),
                    self.fixture(variant, payload=payload) as (run, command, write, output),
                ):
                    with self.assertRaises(RecoveryError):
                        run()
                    self.assert_cleanup(command)
                    write.assert_not_called()
                    self.assertEqual(output.getvalue(), "")

    def test_history_drift_after_http_does_not_publish_receipt(self):
        with self.fixture("assist", drift=True) as (run, command, write, output):
            with self.assertRaisesRegex(RecoveryError, "Histórico mudou"):
                run()
            self.assert_cleanup(command)
            write.assert_not_called()
            self.assertEqual(output.getvalue(), "")
