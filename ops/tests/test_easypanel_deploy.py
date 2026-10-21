from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from ops import easypanel_deploy

ROOT = Path(__file__).resolve().parents[2]


def _service(compose: str, name: str) -> str:
    """Bloco textual de um serviço, até o próximo serviço de primeiro nível."""
    rest = compose.split(f"\n  {name}:\n", 1)[1]
    return re.split(r"\n  [a-z_]+:\n|\nvolumes:\n", rest, maxsplit=1)[0]


def _depends_on(section: str) -> dict[str, str]:
    """Pares serviço -> condição do bloco depends_on de um serviço."""
    block = re.search(r"\n    depends_on:\n((?:      .*\n?)+)", section)
    assert block, "depends_on ausente"
    return dict(re.findall(r"      ([a-z_]+):\n        condition: (\w+)", block.group(1)))


class EasyPanelEnvironmentTests(unittest.TestCase):
    def test_generated_environment_is_private_and_uses_independent_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / ".env.easypanel"
            easypanel_deploy.create_environment(path, "https://ingles.example.com")

            values = easypanel_deploy.validate_private_file(path)
            secrets = [values[key] for key in easypanel_deploy.SECRET_KEYS]

            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(set(secrets)), len(secrets))
            self.assertTrue(all(len(value) == 64 for value in secrets))

    def test_generator_refuses_to_overwrite_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / ".env.easypanel"
            path.write_text("do-not-overwrite", encoding="utf-8")
            with self.assertRaises(easypanel_deploy.ConfigurationError):
                easypanel_deploy.create_environment(path, "https://ingles.example.com")
            self.assertEqual(path.read_text(encoding="utf-8"), "do-not-overwrite")

    def test_invalid_public_origins_are_rejected(self) -> None:
        for origin in (
            "http://ingles.example.com",
            "https://configure-domain.invalid",
            "https://ingles.example.com/rota",
            "https://ingles.example.com:443",
            "https://user:secret@ingles.example.com",
            "https://ingles example.com",
            "https://-ingles.example.com",
        ):
            with (
                self.subTest(origin=origin),
                self.assertRaises(easypanel_deploy.ConfigurationError),
            ):
                easypanel_deploy.validate_origin(origin)

    def test_weak_or_duplicate_secrets_are_rejected(self) -> None:
        values = {
            "EASYPANEL_PUBLIC_ORIGIN": "https://ingles.example.com",
            "EASYPANEL_ASSISTED_FEATURES_ENABLED": "false",
        }
        values.update(
            {
                key: format(index + 1, "064x")
                for index, key in enumerate(easypanel_deploy.SECRET_KEYS)
            }
        )

        weak = dict(values)
        weak[easypanel_deploy.SECRET_KEYS[0]] = "short"
        with self.assertRaises(easypanel_deploy.ConfigurationError):
            easypanel_deploy.validate_values(weak)

        duplicate = dict(values)
        duplicate[easypanel_deploy.SECRET_KEYS[1]] = duplicate[easypanel_deploy.SECRET_KEYS[0]]
        with self.assertRaises(easypanel_deploy.ConfigurationError):
            easypanel_deploy.validate_values(duplicate)

    def test_private_file_rejects_broad_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / ".env.easypanel"
            path.write_text(
                easypanel_deploy.render_environment("https://ingles.example.com"),
                encoding="utf-8",
            )
            os.chmod(path, 0o644)
            with self.assertRaises(easypanel_deploy.ConfigurationError):
                easypanel_deploy.validate_private_file(path)


class EasyPanelArtifactContractTests(unittest.TestCase):
    def test_compose_has_no_fixed_container_names_or_host_ports(self) -> None:
        compose = (ROOT / "infra/easypanel/compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("container_name:", compose)
        self.assertNotIn("\n    ports:", compose)
        self.assertIn('\n    expose:\n      - "80"', compose)

    def test_public_profile_roles_and_release_gates_are_explicit(self) -> None:
        compose = (ROOT / "infra/easypanel/compose.yml").read_text(encoding="utf-8")
        self.assertIn("DEPLOYMENT_PROFILE: public", compose)
        self.assertIn('COOKIE_SECURE: "true"', compose)
        self.assertIn('LEGACY_WRITES_UNTIL: "2026-11-13T00:00:00Z"', compose)
        for role in ("aulas_migrator", "aulas_runtime", "aulas_worker"):
            self.assertIn(role, compose)
        self.assertIn("condition: service_completed_successfully", compose)
        self.assertIn("alembic upgrade head && alembic check", compose)
        self.assertIn("http://127.0.0.1/", compose)
        permissions = compose.split("\n  permissions:\n", 1)[1].split("\n  api:\n", 1)[0]
        self.assertIn("POSTGRES_USER: aulas_migrator", permissions)
        self.assertIn('PGOPTIONS: "-c role=aulas_owner"', permissions)
        self.assertNotIn("EASYPANEL_DB_ADMIN_PASSWORD", permissions)

    def test_seed_runs_after_healthy_api_and_outside_the_release_gate(self) -> None:
        compose = (ROOT / "infra/easypanel/compose.yml").read_text(encoding="utf-8")
        migrate = _service(compose, "migrate")
        self.assertIn("alembic upgrade head && alembic check", migrate)
        self.assertNotIn("seed", migrate.split("command:", 1)[1])
        seed = _service(compose, "seed")
        self.assertIn('command: ["python", "-m", "app.cli", "seed"]', seed)
        self.assertIn("DATABASE_PURPOSE: migrator", seed)
        self.assertIn("aulas_migrator", seed)
        self.assertEqual(_depends_on(seed), {"api": "service_healthy"})
        self.assertIn('restart: "no"', seed)
        # Nem web nem worker esperam o seed: ambos dependem só da API saudável.
        for service in ("worker", "web"):
            self.assertEqual(_depends_on(_service(compose, service)), {"api": "service_healthy"})

    def test_worker_healthcheck_reads_the_heartbeat(self) -> None:
        for path in ("infra/easypanel/compose.yml", "infra/compose.prod.yml", "infra/compose.yml"):
            with self.subTest(path=path):
                compose = (ROOT / path).read_text(encoding="utf-8")
                worker = _service(compose, "worker")
                self.assertIn(
                    'test: ["CMD", "python", "-m", "app.cli", "worker-health"]', worker
                )
                for setting in ("interval: 30s", "timeout: 10s", "retries: 3", "start_period: 40s"):
                    self.assertIn(setting, worker)

    def test_proxy_preserves_external_https_and_only_then_emits_hsts(self) -> None:
        nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
        headers = (ROOT / "frontend/security-headers.conf").read_text(encoding="utf-8")
        self.assertIn("$http_x_forwarded_proto $aulas_forwarded_proto", nginx)
        self.assertIn("proxy_set_header X-Forwarded-Proto $aulas_forwarded_proto", nginx)
        self.assertIn("$aulas_forwarded_proto $aulas_hsts", nginx)
        self.assertIn("Strict-Transport-Security $aulas_hsts", headers)

    def test_proxy_resolves_api_per_request_and_controls_html_cache(self) -> None:
        nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
        directives = "\n".join(
            line for line in nginx.splitlines() if not line.strip().startswith("#")
        )
        api = directives.split("location /api/ {", 1)[1].split("\n    }\n", 1)[0]
        self.assertIn("resolver 127.0.0.11 valid=10s ipv6=off;", api)
        self.assertIn("set $api_upstream http://api:8000;", api)
        self.assertIn("proxy_pass $api_upstream;", api)
        # Um upstream literal seria resolvido uma só vez no boot do nginx.
        self.assertNotIn("proxy_pass http://", directives)
        for exact in ("location = /index.html {", "location = / {", "location = /sw.js {"):
            block = nginx.split(exact, 1)[1].split("\n    }\n", 1)[0]
            self.assertIn('add_header Cache-Control "no-cache, must-revalidate" always;', block)
            self.assertIn("include /etc/nginx/security-headers.conf;", block)
        assets = nginx.split("location /assets/ {", 1)[1].split("\n    }\n", 1)[0]
        self.assertEqual(assets.count("Cache-Control"), 1)
        self.assertIn('add_header Cache-Control "public, max-age=31536000, immutable";', assets)
        self.assertNotIn("expires", assets)
        self.assertIn("try_files $uri $uri/ /index.html;", nginx)


if __name__ == "__main__":
    unittest.main()
