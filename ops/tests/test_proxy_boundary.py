"""Ensaio opt-in de nginx/Uvicorn reais, sem portas públicas ou dados de aluno.

AULAS_PROXY_TEST_IMAGE=nginx:1.28.0-alpine python -m unittest ops.tests.test_proxy_boundary
No CI, usar a imagem web construída do projeto e AULAS_PROXY_TEST_API_IMAGE.
"""

import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
IMAGE = os.environ.get("AULAS_PROXY_TEST_IMAGE")
API_IMAGE = os.environ.get("AULAS_PROXY_TEST_API_IMAGE", "aulas-ingles-api:latest")
SERVER = """
import json,uvicorn
async def app(scope, receive, send):
    payload=json.dumps({"client":scope["client"][0],"scheme":scope["scheme"]}).encode()
    await send({"type":"http.response.start","status":200,
                "headers":[(b"content-type",b"application/json")]})
    await send({"type":"http.response.body","body":payload})
uvicorn.run(app, host="0.0.0.0", port=8000, proxy_headers=True,
            forwarded_allow_ips="*", lifespan="off", access_log=False)
"""
CLIENT = """
import json,urllib.request,urllib.error,sys
from concurrent.futures import ThreadPoolExecutor
settings=json.loads(sys.argv[1])
def request(_):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request=urllib.request.Request("http://web/api/auth/login",headers=settings["headers"])
    try:
        with opener.open(request,timeout=3) as response:
            return {"status":response.status,"body":json.load(response),
                    "hsts":response.headers.get("Strict-Transport-Security")}
    except urllib.error.HTTPError as error:
        return {"status":error.code}
with ThreadPoolExecutor(max_workers=16) as pool:
    results=list(pool.map(request,range(settings.get("count",1))))
print(json.dumps(results))
"""


def docker(*args, check=True):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=60
    )


@unittest.skipUnless(IMAGE, "Defina AULAS_PROXY_TEST_IMAGE para o ensaio Docker isolado.")
class ProxyBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefix = "aulas-proxy-test-" + uuid4().hex[:10]
        cls.api, cls.edge, cls.web = [cls.prefix + suffix for suffix in ("-api", "-edge", "-web")]
        # addClassCleanup também executa quando o setup falha.
        cls.addClassCleanup(cls.cleanup)
        docker("network", "create", "--internal", cls.prefix)
        docker(
            "run",
            "-d",
            "--name",
            cls.api,
            "--network",
            cls.prefix,
            "--network-alias",
            "api",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--entrypoint",
            "python",
            API_IMAGE,
            "-c",
            SERVER,
        )
        docker(
            "run",
            "-d",
            "--name",
            cls.edge,
            "--network",
            cls.prefix,
            "--read-only",
            "--entrypoint",
            "python",
            API_IMAGE,
            "-c",
            "import time; time.sleep(300)",
        )
        cls.api_ip = cls.address(cls.api)
        edge_ip = cls.address(cls.edge)
        mounts = []
        for source, destination in (
            ("frontend/nginx.conf", "/etc/nginx/conf.d/default.conf"),
            ("frontend/api-proxy.conf", "/etc/nginx/api-proxy.conf"),
            ("frontend/security-headers.conf", "/etc/nginx/security-headers.conf"),
            ("frontend/35-trusted-proxies.sh", "/proxy-init.sh"),
        ):
            mounts += ["--mount", f"type=bind,source={ROOT / source},target={destination},readonly"]
        docker(
            "run",
            "-d",
            "--name",
            cls.web,
            "--network",
            cls.prefix,
            "--network-alias",
            "web",
            "--read-only",
            "--tmpfs",
            "/var/run:uid=101,gid=101,mode=0700",
            "--tmpfs",
            "/var/cache/nginx:uid=101,gid=101,mode=0700",
            "--tmpfs",
            "/tmp",
            "--env",
            "AULAS_REQUIRE_TRUSTED_PROXY=true",
            "--env",
            f"AULAS_TRUSTED_PROXY_CIDRS={edge_ip}/32",
            *mounts,
            "--entrypoint",
            "sh",
            IMAGE,
            "-ec",
            "sh /proxy-init.sh; exec /docker-entrypoint.sh nginx -g 'daemon off;'",
        )
        for _ in range(40):
            try:
                if cls.request(cls.edge)[0]["status"] == 200:
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError(docker("logs", cls.web, check=False).stdout)

    @classmethod
    def cleanup(cls):
        for container in (cls.web, cls.edge, cls.api):
            docker("rm", "-f", container, check=False)
        docker("network", "rm", cls.prefix, check=False)

    @classmethod
    def address(cls, container):
        details = json.loads(docker("inspect", container).stdout)[0]
        return details["NetworkSettings"]["Networks"][cls.prefix]["IPAddress"]

    @classmethod
    def request(cls, caller, headers=None, count=1):
        result = docker(
            "exec",
            caller,
            "python",
            "-c",
            CLIENT,
            json.dumps({"headers": headers or {}, "count": count}),
        )
        return json.loads(result.stdout)

    def test_untrusted_peer_cannot_spoof_origin_or_https(self):
        result = self.request(
            self.api, {"X-Forwarded-For": "198.51.100.9", "X-Forwarded-Proto": "https"}
        )[0]
        self.assertEqual(result["body"], {"client": self.api_ip, "scheme": "http"})
        self.assertIsNone(result["hsts"])

    def test_trusted_edge_uses_only_last_address_and_preserves_https(self):
        result = self.request(
            self.edge, {"X-Forwarded-For": "192.0.2.99, 198.51.100.7", "X-Forwarded-Proto": "https"}
        )[0]
        self.assertEqual(result["body"], {"client": "198.51.100.7", "scheme": "https"})
        self.assertIn("max-age", result["hsts"])

    def test_rate_limit_does_not_merge_students_behind_edge(self):
        responses = self.request(self.edge, {"X-Forwarded-For": "198.51.100.30"}, count=180)
        self.assertIn(429, [result["status"] for result in responses])
        other = self.request(self.edge, {"X-Forwarded-For": "198.51.100.31"})[0]
        self.assertEqual(other["status"], 200)

    def test_missing_or_universal_trust_is_rejected(self):
        script = ROOT / "frontend/35-trusted-proxies.sh"
        for ranges in ("", ", ,", "0.0.0.0/0", "::/0", "0.0.0.0/00", "127.0.0.1;include"):
            with self.subTest(ranges=ranges):
                result = docker(
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--tmpfs",
                    "/var/run:uid=101,gid=101,mode=0700",
                    "--env",
                    "AULAS_REQUIRE_TRUSTED_PROXY=true",
                    "--env",
                    f"AULAS_TRUSTED_PROXY_CIDRS={ranges}",
                    "--mount",
                    f"type=bind,source={script},target=/proxy.sh,readonly",
                    "--entrypoint",
                    "sh",
                    IMAGE,
                    "/proxy.sh",
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
