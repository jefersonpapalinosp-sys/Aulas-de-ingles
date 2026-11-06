"""Ensaio opt-in: Compose real, API sintética e nginx de produção, sem dados reais."""

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4

from ops.deploy_release import HEALTH, SERVICES, Releases, run, save

API = os.environ.get("AULAS_DEPLOY_TEST_API_IMAGE", "")
OTHER = os.environ.get("AULAS_DEPLOY_TEST_OTHER_IMAGE", "")
WEB = os.environ.get("AULAS_DEPLOY_TEST_WEB_IMAGE", "")
SERVER = """
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok","db":"up","schema":"compatible"}')
    def log_message(self, *args): pass
HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
"""


@unittest.skipUnless(API and OTHER and WEB, "requer imagens explícitas e Docker Compose Linux")
class DeployRuntimeTests(unittest.TestCase):
    def test_real_rollback_and_unprivileged_nginx_preserve_volume(self):
        project = "aulas-dr-deploy55-" + uuid4().hex[:12]
        ids = {
            name: run(["docker", "image", "inspect", "--format", "{{.Id}}", image]).decode().strip()
            for name, image in (("old", API), ("new", OTHER), ("web", WEB))
        }
        self.assertNotEqual(ids["old"], ids["new"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = root / "private.env"
            env.write_text("SYNTHETIC=true\n")
            env.chmod(0o600)
            override = root / "override.json"
            save(override, {"services": {}})
            release = Releases(
                {
                    "project": project,
                    "repository": str(root / "repo"),
                    "state": str(root / "state"),
                    "env_file": str(env),
                    "override_file": str(override),
                    "existing_code": str(root / "code"),
                }
            )
            services = {
                "api": {
                    "entrypoint": ["python", "-u", "-c", SERVER],
                    "healthcheck": {"test": ["CMD", "python", "-c", HEALTH], "interval": "1s"},
                },
                "worker": {"entrypoint": ["python", "-c", "import time; time.sleep(3600)"]},
                "web": {
                    "user": "101:101",
                    "read_only": True,
                    "cap_drop": ["ALL"],
                    "security_opt": ["no-new-privileges:true"],
                    "sysctls": {"net.ipv4.ip_unprivileged_port_start": "0"},
                    "tmpfs": [
                        "/var/run:uid=101,gid=101,mode=0700",
                        "/var/cache/nginx:uid=101,gid=101,mode=0700",
                    ],
                    "environment": {
                        "AULAS_ASSET_ARCHIVE": "/var/lib/aulas-web",
                        "AULAS_REQUIRE_TRUSTED_PROXY": "true",
                        "AULAS_TRUSTED_PROXY_CIDRS": "127.0.0.1/32",
                    },
                    "volumes": ["web_assets:/var/lib/aulas-web"],
                    "healthcheck": {
                        "test": ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1/"],
                        "interval": "1s",
                    },
                },
            }
            for name, identity in (("baseline", ids["old"]), ("candidate", ids["new"])):
                directory = release.state / "releases" / name
                compose = directory / "infra/easypanel/compose.yml"
                compose.parent.mkdir(parents=True)
                save(compose, {"services": services, "volumes": {"web_assets": {}}})
                images = {"api": identity, "worker": identity, "web": ids["web"]}
                save(
                    directory / "images.json",
                    {"services": {s: {"image": v} for s, v in images.items()}},
                )
                save(
                    release.state / ("previous.json" if name == "baseline" else "current.json"),
                    {"release": name, "images": images},
                )
            candidate = release.location(release.receipt("current"))
            try:
                result = subprocess.run(
                    release.compose(
                        candidate,
                        "up",
                        "-d",
                        "--no-build",
                        "--pull",
                        "never",
                        "--wait",
                        "--wait-timeout",
                        "60",
                        *SERVICES,
                    ),
                    capture_output=True,
                    text=True,
                    timeout=90,
                    check=False,
                )
                if result.returncode:
                    print(run(release.compose(candidate, "logs", "--tail", "30")).decode())
                self.assertEqual(result.returncode, 0, result.stderr)
                web = f"{project}-web-1"
                status = run(["docker", "exec", web, "cat", "/proc/1/status"]).decode()
                self.assertIn("Uid:\t101\t101\t101\t101", status)
                self.assertIn("CapEff:\t0000000000000000", status)
                run(
                    [
                        "docker",
                        "exec",
                        web,
                        "sh",
                        "-ec",
                        "printf preserved > /var/lib/aulas-web/marker",
                    ]
                )
                before = release.images()
                started = time.monotonic()
                release.rollback()
                elapsed = time.monotonic() - started
                self.assertLess(elapsed, 300)
                self.assertNotEqual(before["api"], release.images()["api"])
                self.assertEqual(release.images(), release.receipt("previous")["images"])
                self.assertEqual(
                    run(["docker", "exec", web, "cat", "/var/lib/aulas-web/marker"]), b"preserved"
                )
                print(
                    json.dumps(
                        {
                            "lab": project,
                            "rollback_seconds": round(elapsed, 3),
                            "nginx_uid": 101,
                            "capabilities": 0,
                            "volume_preserved": True,
                        }
                    )
                )
            finally:
                # Somente recursos do projeto UUID criado acima, nunca a stack de estudo.
                run(release.compose(candidate, "down", "--volumes", "--remove-orphans"))
