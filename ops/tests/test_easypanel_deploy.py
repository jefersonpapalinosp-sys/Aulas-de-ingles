from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ops import easypanel_deploy

ROOT = Path(__file__).resolve().parents[2]


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

    def test_proxy_preserves_external_https_and_only_then_emits_hsts(self) -> None:
        nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
        headers = (ROOT / "frontend/security-headers.conf").read_text(encoding="utf-8")
        self.assertIn("$http_x_forwarded_proto $aulas_forwarded_proto", nginx)
        self.assertIn("proxy_set_header X-Forwarded-Proto $aulas_forwarded_proto", nginx)
        self.assertIn("$aulas_forwarded_proto $aulas_hsts", nginx)
        self.assertIn("Strict-Transport-Security $aulas_hsts", headers)


if __name__ == "__main__":
    unittest.main()
