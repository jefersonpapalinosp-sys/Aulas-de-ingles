"""Opt-in: docker stop real durante um diálogo, em banco descartável já preparado."""

import os
import subprocess
import time
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get("AULAS_WORKER_TEST_IMAGE"), "Laboratório Docker opt-in")
class WorkerShutdownTest(unittest.TestCase):
    def test_docker_stop_drains_one_attempt_and_leaves_next_queued(self):
        image = os.environ["AULAS_WORKER_TEST_IMAGE"]
        network = os.environ["AULAS_WORKER_TEST_NETWORK"]
        host = os.environ["AULAS_WORKER_TEST_DB_HOST"]
        run_id = str(uuid4())
        name = f"aulas-worker-stop-{run_id}"
        common = [
            "--network",
            network,
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--env",
            "APP_ENV=test",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONPATH=/work/backend",
            "--env",
            f"DATABASE_URL=postgresql+asyncpg://aulas_test:aulas_test_only@{host}:5432/aulas_ingles_test",
            "--mount",
            f"type=bind,source={ROOT},target=/work,readonly",
            "--workdir",
            "/work/backend",
            "--entrypoint",
            "python",
        ]

        def docker(*args):
            return subprocess.run(
                ["docker", *args], text=True, capture_output=True, check=True, timeout=45
            ).stdout

        def fixture(action):
            return docker(
                "run", "--rm", *common, image, "tests/worker_shutdown_fixture.py", action, run_id
            )

        try:
            fixture("setup")
            docker(
                "run",
                "-d",
                "--name",
                name,
                *common,
                image,
                "tests/worker_shutdown_fixture.py",
                "run",
                run_id,
            )
            deadline = time.monotonic() + 20
            while "S53_PROVIDER_ENTERED" not in docker("logs", name):
                if time.monotonic() > deadline:
                    self.fail("Worker não iniciou o provedor sintético")
                time.sleep(0.1)
            docker("stop", "--time", "15", name)
            self.assertEqual(
                docker("inspect", "--format", "{{.State.ExitCode}}", name).strip(), "0"
            )
            self.assertIn("S53_STOP_VERIFIED", fixture("check"))
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name], capture_output=True, check=False, timeout=15
            )
            fixture("cleanup")


if __name__ == "__main__":
    unittest.main()
