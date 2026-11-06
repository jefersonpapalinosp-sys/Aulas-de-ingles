import contextlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops import deploy_release, security_gate
from ops.recovery_archive import RecoveryError

OLD = "sha256:" + "1" * 64
NEW = "sha256:" + "2" * 64
SHA = "a" * 40


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = self.root / "private.env"
        env.write_text("SYNTHETIC=true")
        env.chmod(0o600)
        self.config = {
            "project": "aulas-dr-release55",
            "repository": str(self.root / "repo"),
            "state": str(self.root / "state"),
            "env_file": str(env),
            "override_file": str(self.root / "override.yml"),
            "existing_code": str(self.root / "code"),
        }
        self.release = deploy_release.Releases(self.config)
        baseline = self.release.state / "releases/baseline"
        baseline.mkdir()
        self.record = {"release": "baseline", "images": {s: OLD for s in deploy_release.SERVICES}}
        deploy_release.save(self.release.state / "current.json", self.record)
        self.calls = []
        self.failure = None
        self.live = OLD

    def fake_run(self, command, **kwargs):
        self.calls.append(command)
        if self.failure and self.failure(command):
            raise RecoveryError("synthetic failure")
        if command[:3] == ["git", "archive", "--format=tar"]:
            with tarfile.open(command[4], "w") as archive:
                info = tarfile.TarInfo("infra/easypanel/compose.yml")
                body = b"services: {}\n"
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
        if command[:2] == ["docker", "inspect"]:
            return self.live.encode()
        if command[:3] == ["docker", "image", "inspect"]:
            return NEW.encode()
        if command[:2] == ["docker", "compose"] and "run" in command and "-d" in command:
            return ("f" * 64).encode()
        if command[:2] == ["docker", "compose"] and "up" in command:
            self.live = OLD if "baseline" in " ".join(command) else NEW
        return b""

    def deploy(self):
        with (
            patch.object(deploy_release, "run", side_effect=self.fake_run),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.release.deploy(SHA)

    def test_build_and_scan_finish_before_worker_stop_or_migration(self):
        self.deploy()
        build = next(i for i, c in enumerate(self.calls) if c[-1] == "build")
        scan = max(i for i, c in enumerate(self.calls) if c[0] == "trivy")
        stop = next(i for i, c in enumerate(self.calls) if c[-2:] == ["stop", "worker"])
        self.assertLess(build, scan)
        self.assertLess(scan, stop)
        up = next(c for c in self.calls if c[:2] == ["docker", "compose"] and "up" in c)
        self.assertIn("--no-build", up)
        self.assertIn("--no-deps", up)
        self.assertNotIn("db", up[up.index("up") :])
        self.assertEqual(self.release.receipt("previous"), self.record)
        self.assertEqual(self.release.receipt("current")["images"]["api"], NEW)
        self.assertFalse((self.release.state / "pending.json").exists())
        self.assertEqual(
            json.loads((self.release.state / "phase.json").read_text())["phase"], "release-ready"
        )

    def test_build_and_scanner_failure_preserve_live_release_and_do_not_migrate(self):
        for stage in ("build", "trivy"):
            self.calls.clear()
            self.failure = lambda c, stage=stage: c[-1] == stage or c[0] == stage
            with self.subTest(stage=stage), self.assertRaises(RecoveryError):
                self.deploy()
            self.assertEqual(self.release.receipt("current"), self.record)
            self.assertFalse(any("stop" in c for c in self.calls))
            self.assertFalse((self.release.state / "pending.json").exists())

    def test_migration_failure_keeps_previous_and_pending_for_explicit_recovery(self):
        self.failure = lambda c: "run" in c and c[-1] == "migrate"
        with self.assertRaises(RecoveryError):
            self.deploy()
        self.assertEqual(self.release.receipt("current"), self.record)
        self.assertTrue((self.release.state / "pending.json").exists())
        self.assertFalse(any("up" in c for c in self.calls))

    def test_rollback_probes_compatibility_and_never_runs_build_migration_or_seed(self):
        self.deploy()
        self.calls.clear()
        with (
            patch.object(deploy_release, "run", side_effect=self.fake_run),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.release.rollback()
        self.assertFalse(
            any(c[-1] in {"build", "migrate", "seed", "permissions"} for c in self.calls)
        )
        self.assertEqual(self.release.receipt("current"), self.record)
        probe = next(i for i, c in enumerate(self.calls) if c[:2] == ["docker", "exec"])
        up = next(i for i, c in enumerate(self.calls) if "up" in c)
        self.assertLess(probe, up)

    def test_incompatible_rollback_does_not_replace_running_containers(self):
        self.deploy()
        self.calls.clear()
        self.failure = lambda c: c[:2] == ["docker", "exec"]
        with (
            patch.object(deploy_release, "run", side_effect=self.fake_run),
            patch.object(deploy_release.time, "sleep"),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(RecoveryError),
        ):
            self.release.rollback()
        self.assertFalse(any("up" in c or "stop" in c for c in self.calls))
        self.assertTrue(any(c[:3] == ["docker", "rm", "-f"] for c in self.calls))

    def test_lock_refuses_a_second_process_and_releases_on_error(self):
        path = self.root / "lock"
        with (
            deploy_release.lock(path),
            self.assertRaises(BlockingIOError),
            deploy_release.lock(path),
        ):
            pass
        with self.assertRaises(RuntimeError), deploy_release.lock(path):
            raise RuntimeError("synthetic")
        with deploy_release.lock(path):
            pass

    def test_archive_rejects_traversal_links_and_private_files(self):
        for name, kind in (
            ("../escape", tarfile.REGTYPE),
            ("link", tarfile.SYMTYPE),
            ("secrets/key", tarfile.REGTYPE),
            (".env.prod", tarfile.REGTYPE),
        ):
            archive = self.root / "source.tar"
            with tarfile.open(archive, "w") as tar:
                info = tarfile.TarInfo(name)
                info.type = kind
                tar.addfile(info)
            with self.subTest(name=name), self.assertRaises(RecoveryError):
                deploy_release.extract(archive, self.root / "out")


class SecurityGateTests(unittest.TestCase):
    def test_critical_and_missing_or_malformed_reports_block(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            base = {
                "SchemaVersion": 2,
                "ArtifactType": "container_image",
                "Results": [{"Target": "synthetic", "Vulnerabilities": []}],
            }
            path.write_text(json.dumps(base))
            self.assertEqual(security_gate.main([str(path), str(path)]), 0)
            base["Results"][0]["Vulnerabilities"] = [{"Severity": "CRITICAL"}]
            path.write_text(json.dumps(base))
            self.assertEqual(security_gate.main([str(path), str(path)]), 1)
            for value in (
                {},
                {**base, "Results": []},
                {**base, "Results": [{"Target": "x", "Vulnerabilities": False}]},
            ):
                path.write_text(json.dumps(value))
                self.assertEqual(security_gate.main([str(path), str(path)]), 1)
            self.assertEqual(security_gate.main([str(path), str(path.parent / "missing")]), 1)
