import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
SHM_256_MIB = 256 * 1024 * 1024

SYNTHETIC_ENV = """\
POSTGRES_PASSWORD=synthetic-compose-check-password
DATABASE_URL=postgresql+asyncpg://synthetic:synthetic@db:5432/aulas_ingles
JWT_SECRET=synthetic-compose-check-secret-at-least-32-bytes
RUNTIME_DATABASE_URL=postgresql+asyncpg://runtime:synthetic@db:5432/aulas_ingles
WORKER_DATABASE_URL=postgresql+asyncpg://worker:synthetic@db:5432/aulas_ingles
MIGRATOR_DATABASE_URL=postgresql+asyncpg://migrator:synthetic@db:5432/aulas_ingles
EASYPANEL_PUBLIC_ORIGIN=https://compose-check.invalid
EASYPANEL_TRUSTED_PROXY_CIDRS=192.0.2.10/32
EASYPANEL_JWT_SECRET=synthetic-easypanel-jwt-secret-at-least-32-bytes
EASYPANEL_OPERATIONS_TOKEN=synthetic-operations-token-at-least-32-bytes
EASYPANEL_DB_ADMIN_PASSWORD=synthetic-admin-password
EASYPANEL_MIGRATOR_PASSWORD=synthetic-migrator-password
EASYPANEL_RUNTIME_PASSWORD=synthetic-runtime-password
EASYPANEL_WORKER_PASSWORD=synthetic-worker-password
EASYPANEL_BACKUP_PASSWORD=synthetic-backup-password
"""

# Nome, arquivos que formam o projeto Compose, bancos PostgreSQL reais e APIs.
CASES = (
    ("dev", (INFRA / "compose.yml",), ("db",), ("api",)),
    ("study", (INFRA / "compose.prod.yml",), ("db",), ("api",)),
    (
        "study-roles",
        (INFRA / "compose.prod.yml", INFRA / "compose.roles.prod.yml"),
        ("db",),
        ("api",),
    ),
    ("e2e", (INFRA / "compose.e2e.yml",), ("db",), ("api",)),
    ("test", (INFRA / "compose.test.yml",), ("db",), ()),
    (
        "recovery",
        (INFRA / "compose.recovery.yml",),
        ("source-db", "target-db", "study-check-db", "concurrency-check-db"),
        (),
    ),
    (
        "recovery48",
        (INFRA / "compose.recovery48.yml",),
        ("source-db", "target-db"),
        (),
    ),
    (
        "upgrade",
        (INFRA / "compose.upgrade.yml",),
        ("source-db", "target-db"),
        (),
    ),
    ("roles", (INFRA / "compose.roles.yml",), ("db",), ()),
    ("rotation", (INFRA / "compose.rotation.yml",), ("db",), ()),
    (
        "legacy-rehearsal",
        (INFRA / "compose.legacy-rehearsal.yml",),
        ("assist-check-db", "dev-check-db"),
        (),
    ),
    (
        "easypanel",
        (INFRA / "easypanel" / "compose.yml",),
        ("db",),
        ("api",),
    ),
)


def _compose_command() -> list[str] | None:
    standalone = shutil.which("docker-compose")
    if standalone:
        return [standalone]
    docker = shutil.which("docker")
    if not docker:
        return None
    probe = subprocess.run(
        [docker, "compose", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [docker, "compose"] if probe.returncode == 0 else None


class ComposeRuntimeLimitsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = _compose_command()
        if cls.compose is None:
            raise unittest.SkipTest("Docker Compose CLI não está disponível.")
        cls.temporary = tempfile.TemporaryDirectory(prefix="aulas-compose-config-")
        temporary = Path(cls.temporary.name)
        cls.env_file = temporary / "synthetic.env"
        cls.env_file.write_text(SYNTHETIC_ENV, encoding="utf-8")
        cls.process_env = os.environ.copy()
        cls.process_env.update(line.split("=", 1) for line in SYNTHETIC_ENV.splitlines() if line)
        cls.process_env["DOCKER_CONFIG"] = str(temporary / "docker-config")
        Path(cls.process_env["DOCKER_CONFIG"]).mkdir()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _config(self, files: tuple[Path, ...]) -> dict[str, object]:
        command = [*self.compose, "--env-file", str(self.env_file)]
        for compose_file in files:
            command.extend(("-f", str(compose_file)))
        command.extend(("--profile", "*", "config", "--format", "json"))
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=self.process_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_every_compose_file_is_covered(self) -> None:
        covered = {path.resolve() for _, files, _, _ in CASES for path in files}
        discovered = {path.resolve() for path in INFRA.glob("compose*.yml")}
        discovered.add((INFRA / "easypanel" / "compose.yml").resolve())
        self.assertEqual(covered, discovered)

    def test_all_services_rotate_logs_and_limit_processes(self) -> None:
        for name, files, _, _ in CASES:
            with self.subTest(compose=name):
                services = self._config(files)["services"]
                for service_name, service in services.items():
                    with self.subTest(compose=name, service=service_name):
                        self.assertEqual(service.get("pids_limit"), 256)
                        logging = service.get("logging", {})
                        self.assertEqual(logging.get("driver"), "json-file")
                        self.assertEqual(logging.get("options", {}).get("max-size"), "10m")
                        self.assertEqual(logging.get("options", {}).get("max-file"), "3")

    def test_postgres_servers_receive_256_mib_shared_memory(self) -> None:
        for name, files, database_services, _ in CASES:
            with self.subTest(compose=name):
                services = self._config(files)["services"]
                for service_name in database_services:
                    self.assertEqual(int(services[service_name].get("shm_size", 0)), SHM_256_MIB)

    def test_api_container_healthchecks_are_liveness_only(self) -> None:
        for name, files, _, api_services in CASES:
            with self.subTest(compose=name):
                services = self._config(files)["services"]
                for service_name in api_services:
                    test = " ".join(services[service_name]["healthcheck"]["test"])
                    self.assertIn("/api/live", test)
                    self.assertNotIn("/api/health", test)

    def test_database_diagnostics_and_worker_shutdown_grace(self) -> None:
        for name, files, database_services, _ in CASES:
            with self.subTest(compose=name):
                services = self._config(files)["services"]
                for service_name in database_services:
                    command = services[service_name]["command"]
                    self.assertIn("log_lock_waits=on", command)
                    self.assertIn("idle_in_transaction_session_timeout=60000", command)
                    self.assertIn("log_parameter_max_length=0", command)
                    self.assertIn("log_parameter_max_length_on_error=0", command)
                if "worker" in services:
                    self.assertEqual(services["worker"]["stop_grace_period"], "2m30s")
                    expected_processes = "2" if name == "dev" else "3"
                    for process in ("api", "worker"):
                        self.assertEqual(
                            str(services[process]["environment"]["DATABASE_PROCESS_BUDGET"]),
                            expected_processes,
                        )
                    for volume in services["worker"].get("volumes", []):
                        if volume.get("target") == "/app/data/speaking":
                            self.assertFalse(volume.get("read_only", False))


if __name__ == "__main__":
    unittest.main()
