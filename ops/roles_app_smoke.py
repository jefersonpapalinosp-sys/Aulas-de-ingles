"""Executado no helper runtime do laboratório; servidor só em loopback dentro do container."""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from uuid import uuid4


def request(
    path: str, payload: object = None, method: str = "GET", token: str | None = None
) -> object:
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


def as_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Resposta da API deve ser um objeto JSON.")
    return dict(value)


def object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError("Resposta da API deve ser uma lista JSON.")
    return [as_object(item) for item in value]


def object_request(
    path: str, payload: object = None, method: str = "GET", token: str | None = None
) -> dict[str, object]:
    return as_object(request(path, payload, method, token))


def main() -> None:
    assert os.environ["DATABASE_PURPOSE"] == "runtime"
    assert os.environ["DATABASE_URL"].endswith("@db:5432/aulas_roles_lab")
    # This process is restricted to the synthetic roles lab above.
    os.environ["EDITORIAL_SNAPSHOTS_ENABLED"] = "true"
    server = subprocess.Popen(
        ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                assert object_request("/health")["db"] == "up"
                break
            except (urllib.error.URLError, AssertionError):
                time.sleep(0.1)
        else:
            raise RuntimeError("API de papéis não ficou pronta.")
        token = object_request(
            "/auth/register",
            {
                "email": f"roles-{uuid4().hex}@example.com",
                "password": "synthetic-long-password",
                "display_name": "Role probe",
            },
            "POST",
        )["access_token"]
        assert isinstance(token, str) and token
        lesson = object_request("/lessons/31")
        attempt = object_request(
            f"/exercises/{object_list(lesson['exercises'])[0]['id']}/attempt",
            {"answer": "should", "idempotency_key": str(uuid4())},
            "POST",
            token,
        )
        snapshot = object_request(
            f"/me/history/exercise/{attempt['attempt_id']}/content", token=token
        )
        assert snapshot["status"] == "available"
        content = as_object(snapshot["content"])
        assert content["source_id"] == object_list(lesson["exercises"])[0]["id"]
        assert content["editorial_identity_contract"] == "explicit_uuid_v1"
        editorial_key = content["editorial_key"]
        assert isinstance(editorial_key, str) and len(editorial_key) == 36
        activity = object_request(
            "/me/activity/sessions",
            {"session_id": str(uuid4()), "lesson_id": lesson["id"]},
            "POST",
            token,
        )
        event = {
            "session_id": activity["session_id"],
            "operation_key": str(uuid4()),
            "end_offset_ms": 1,
            "duration_ms": 1,
        }
        receipt = object_request("/me/activity/events", event, "POST", token)
        assert receipt == object_request("/me/activity/events", event, "POST", token)
        assert receipt["credited_ms"] == 1
        media = f"/media/{object_list(lesson['media'])[0]['id']}/position"
        position = {
            "position_seconds": 42,
            "expected_revision": 0,
            "operation_key": str(uuid4()),
            "changed_at": datetime.now(UTC).isoformat(),
        }
        assert object_request(media, position, "PUT", token)["revision"] == 1
        assert (
            object_request("/me/today", token=token)["time_measurement"] == "active_intervals_v1"
        )
        assert len(object_list(object_request("/me/export", token=token)["activity_events"])) == 1
        prompt = object_list(lesson["writing_prompts"])[0]["id"]
        base = f"/writing/prompts/{prompt}"
        text = "The metro is faster than the bus. Visitors should take it."
        assert (
            object_request(base + "/draft", {"text": text, "expected_revision": 0}, "PUT", token)[
                "text"
            ]
            == text
        )
        object_request(base + "/versions", {"text": text, "expected_revision": 1}, "POST", token)
        feedback = object_request(base + "/feedback", {"text": text}, "POST", token)
        historical = object_request(f"/me/history/writing/{feedback['id']}/content", token=token)
        assert historical["status"] == "available"
        assert object_request("/assist/status", token=token)["reserved_today"] == 0
        object_request("/auth/me", token=token)
        object_request(
            "/review/items/" + str(object_list(lesson["vocab"])[0]["id"]), {}, "POST", token
        )
        item = object_list(request("/review/due", token=token))[0]
        body = {
            "quality": 4,
            "expected_revision": item["revision"],
            "idempotency_key": str(uuid4()),
        }
        result = object_request("/review/" + str(item["id"]) + "/grade", body, "POST", token)
        assert result == object_request(
            "/review/" + str(item["id"]) + "/grade", body, "POST", token
        )
        print(
            "HTTP runtime: cadastro, escrita, revisão, áudio, atividade e exportação aprovados."
        )
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
