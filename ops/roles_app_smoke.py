"""Executado no helper runtime do laboratório; servidor só em loopback dentro do container."""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4

assert os.environ["DATABASE_PURPOSE"] == "runtime"
assert os.environ["DATABASE_URL"].endswith("@db:5432/aulas_roles_lab")


def request(path, payload=None, method="GET", token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"http://127.0.0.1:8000/api{path}",
        headers=headers,
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
    )
    with urllib.request.urlopen(req, timeout=10) as result:
        return json.load(result)


server = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
try:
    for _ in range(100):
        try:
            assert request("/health")["db"] == "up"
            break
        except (urllib.error.URLError, AssertionError):
            time.sleep(0.1)
    else:
        raise RuntimeError("API de papéis não ficou pronta.")
    token = request(
        "/auth/register",
        {
            "email": f"roles-{uuid4().hex}@example.com",
            "password": "synthetic-long-password",
            "display_name": "Role probe",
        },
        "POST",
    )["access_token"]
    lesson = request("/lessons/31")
    prompt = lesson["writing_prompts"][0]["id"]
    base = f"/writing/prompts/{prompt}"
    text = "The metro is faster than the bus. Visitors should take it."
    assert (
        request(base + "/draft", {"text": text, "expected_revision": 0}, "PUT", token)["text"]
        == text
    )
    request(base + "/versions", {"text": text, "expected_revision": 1}, "POST", token)
    request(base + "/feedback", {"text": text}, "POST", token)
    request("/auth/me", token=token)
    request("/review/items/" + str(lesson["vocab"][0]["id"]), {}, "POST", token)
    item = request("/review/due", token=token)[0]
    body = {"quality": 4, "expected_revision": item["revision"], "idempotency_key": str(uuid4())}
    result = request("/review/" + str(item["id"]) + "/grade", body, "POST", token)
    assert result == request("/review/" + str(item["id"]) + "/grade", body, "POST", token)
    print("HTTP runtime: cadastro, leitura, rascunho, versão, feedback e perfil aprovados.")
finally:
    server.terminate()
    server.wait(timeout=10)
