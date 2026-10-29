"""Guardas SEC-49 e recibo sem segredos; Docker/banco/HTTP são simulados."""

import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops import recovery
from ops import rotation_probe as probe
from ops import rotation_rehearsal as rotation
from ops.recovery_archive import RecoveryError


def container():
    return {
        "State": {"Running": True},
        "HostConfig": {"Privileged": False, "PortBindings": {}},
        "Config": {"Image": recovery.POSTGRES},
        "NetworkSettings": {"Networks": {rotation.NETWORK: {}}},
        "Mounts": [
            {"Type": "volume", "Name": rotation.VOLUME, "Destination": "/var/lib/postgresql/data"},
            {
                "Type": "bind",
                "RW": False,
                "Source": str(recovery.ROOT / "infra/rotation-db-init.sql"),
                "Destination": "/docker-entrypoint-initdb.d/01-rotation.sql",
            },
        ],
    }


def report():
    return {**probe.EXPECTED, **dict.fromkeys(probe.TIMINGS, 10)}


class RotationTests(unittest.TestCase):
    def test_topology_refuses_ports_foreign_network_mounts_and_privileges(self):
        good = container()
        rotation.validate_container(good)
        cases = []
        for group, key, value in (
            ("HostConfig", "PortBindings", {"5432/tcp": [{}]}),
            ("HostConfig", "Privileged", True),
            ("State", "Running", False),
            ("Config", "Image", "untrusted"),
            ("NetworkSettings", "Networks", {"aulas-ingles-prod_default": {}}),
        ):
            changed = copy.deepcopy(good)
            changed[group][key] = value
            cases.append(changed)
        for key, value in (("RW", True), ("Source", "/private/credentials")):
            changed = copy.deepcopy(good)
            changed["Mounts"][1][key] = value
            cases.append(changed)
        changed = copy.deepcopy(good)
        changed["Mounts"][0]["Name"] = "aulas-ingles-prod_pgdata"
        cases.append(changed)
        for changed in cases:
            with self.subTest(changed=changed), self.assertRaises(RecoveryError):
                rotation.validate_container(changed)

    def test_network_must_be_internal_and_owned_by_rotation(self):
        good = {
            "Name": rotation.NETWORK,
            "Driver": "bridge",
            "Internal": True,
            "Labels": {"com.docker.compose.project": rotation.PROJECT},
        }
        rotation.validate_network(good)
        for key, value in (
            ("Name", "other"),
            ("Driver", "overlay"),
            ("Internal", False),
            ("Labels", {"com.docker.compose.project": "aulas-ingles-prod"}),
        ):
            with self.subTest(key=key), self.assertRaises(RecoveryError):
                rotation.validate_network({**good, key: value})

    def test_probe_refuses_wrong_environment_before_any_connection(self):
        for env in ({}, {"ROTATION_LAB": rotation.MARKER, "APP_ENV": "prod"}):
            with patch.dict("os.environ", env, clear=True), patch.object(probe, "engine") as engine:
                with self.assertRaises(RecoveryError):
                    asyncio.run(probe.run())
                engine.assert_not_called()

    def test_report_refuses_missing_checks_wrong_types_and_secret_fields(self):
        good = report()
        self.assertEqual(probe.validate_report(good), good)
        variants = [
            None,
            [],
            {},
            {**good, "password": "never-log-me"},
            {**good, "jwt_old_access_status": 200},
            {**good, "verified": 1},
            {**good, "provider_calls": True},
            {**good, "jwt_ms": -1},
            {**good, "password_ms": 300001},
            {**good, "total_ms": "private"},
        ]
        for value in variants:
            with self.subTest(value=value), self.assertRaises(RecoveryError) as error:
                probe.validate_report(value)
            self.assertNotIn("never-log-me", str(error.exception))

    def test_failed_probe_cleans_only_created_container_and_never_writes_receipt(self):
        identifier = "a" * 64
        for failure in (
            RecoveryError("failure"),
            json.dumps({**report(), "token": "secret"}).encode(),
        ):
            with (
                tempfile.TemporaryDirectory() as directory,
                patch.object(rotation, "resources"),
                patch.object(recovery, "container", return_value=container()),
                patch.object(rotation, "receipt_root", return_value=Path(directory)),
                patch.object(
                    recovery, "docker", side_effect=[identifier.encode(), failure, b""]
                ) as docker,
                patch.object(rotation, "write_json") as write,
                self.assertRaises(RecoveryError),
            ):
                rotation.run_probe()
            self.assertEqual(docker.call_args.args, ("rm", "-f", identifier))
            write.assert_not_called()
            args = docker.call_args_list[0].args
            self.assertIn("--read-only", args)
            self.assertNotIn("--env-file", args)
            self.assertNotIn("-p", args)

    def test_existing_probe_is_not_removed_if_create_fails(self):
        with (
            patch.object(rotation, "resources"),
            patch.object(recovery, "container", return_value=container()),
            patch.object(rotation, "receipt_root"),
            patch.object(
                recovery, "docker", side_effect=RecoveryError("name already used")
            ) as docker,
            self.assertRaises(RecoveryError),
        ):
            rotation.run_probe()
        self.assertEqual(docker.call_count, 1)
        self.assertEqual(docker.call_args.args[0], "create")

    def test_success_publishes_only_verified_aggregate_receipt(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(rotation, "resources"),
            patch.object(recovery, "container", return_value=container()),
            patch.object(rotation, "receipt_root", return_value=Path(directory)),
            patch.object(
                recovery, "docker", side_effect=[b"a" * 64, json.dumps(report()).encode(), b""]
            ),
        ):
            result = rotation.run_probe()
            files = list(Path(directory).glob("rotation49-*.json"))
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text()), result)
            self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
            self.assertTrue(result["verified"])
