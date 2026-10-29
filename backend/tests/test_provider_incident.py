"""SEC-48: revogação, pausa e retomada contra gateway HTTP só de loopback.

Credenciais e conteúdo são sintéticos. Não altera ambiente, painel ou provedor
real. A API e o worker usam o banco protegido pelas fixtures de teste.
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import FormatadorJson
from app.db.models import AssistReservation, TranscriptionJob
from app.services import transcription_queue
from tests.audio_samples import wav
from tests.test_auth import auth, registrar
from tests.test_dialogue_routes import _criar

OLD_TOKEN = "synthetic-revoked-sec48-token"
NEW_TOKEN = "synthetic-replacement-sec48-token"
STUDENT_TEXT = "The quiet subway reaches my private station."
PARTNER_TEXT = "Do you take the subway every morning?"
ERROR_BODY = "synthetic-sensitive-provider-error-content"


@pytest.fixture
def incident_gateway():
    state = {"token": OLD_TOKEN, "unavailable": False, "calls": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            authorized = self.headers.get("Authorization") == f"Bearer {state['token']}"
            # Somente metadados; não reter cabeçalhos ou conteúdo enviado.
            state["calls"].append((self.path, authorized, self.headers.get("Idempotency-Key")))
            status = 401 if not authorized else 503 if state["unavailable"] else 200
            payload = (
                {"error": ERROR_BODY, "detail": OLD_TOKEN}
                if status != 200
                else {
                    "text": STUDENT_TEXT,
                    "words": [{"text": "subway", "start_ms": 0, "end_ms": 200, "confidence": 0.9}],
                    "cost_microusd": 3,
                }
                if self.path == "/stt"
                else {
                    "result": {
                        "response": {
                            "partner_text": PARTNER_TEXT,
                            "hints": [],
                            "confidence": 0.9,
                        }
                    },
                    "cost_microusd": 7,
                }
            )
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("input_kind", ["text", "audio"])
async def test_incidente_revoga_token_pausa_fila_e_retoma_sem_vazar_logs(
    client,
    session,
    monkeypatch,
    tmp_path,
    caplog,
    incident_gateway,
    input_kind,
):
    base, gateway = incident_gateway
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_provider_kind", "gateway")
    monkeypatch.setattr(settings, "assist_provider_token", OLD_TOKEN)
    monkeypatch.setattr(settings, "assist_provider_name", "synthetic-incident")
    monkeypatch.setattr(settings, "assist_dialogue_url", f"{base}/dialogue")
    monkeypatch.setattr(settings, "assist_transcription_url", f"{base}/stt")
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    caplog.set_level(logging.INFO)
    headers = auth(await registrar(client, f"sec48-{input_kind}"))
    _, conversation = await _criar(client, headers, mode="guided")
    route = f"/api/speaking/dialogues/{conversation['id']}"

    async def enqueue(position):
        if input_kind == "text":
            response = await client.post(
                f"{route}/turns/{position}/text",
                headers=headers,
                json={"text": STUDENT_TEXT, "idempotency_key": str(uuid4())},
            )
        else:
            response = await client.put(
                f"{route}/turns/{position}/audio",
                content=wav(),
                headers={**headers, "Content-Type": "audio/wav", "X-Audio-Consent": "true"},
            )
        assert response.status_code == 202, response.text
        return response.json()["job_id"]

    async def turn(position):
        response = await client.get(f"{route}/turns/{position}", headers=headers)
        assert response.status_code == 200
        return response.json()

    await enqueue(1)
    assert await transcription_queue.process_next_transcription()
    assert (await turn(1))["state"] == "completed"
    assert (await turn(1))["fallback"] is False

    # A revogação é aplicada no gateway antes de trocar a credencial do worker.
    await enqueue(2)
    gateway["token"] = NEW_TOKEN
    assert await transcription_queue.process_next_transcription()
    revoked = await turn(2)
    assert revoked["error_code"] == "provider_unavailable"
    assert revoked["state"] == ("completed" if input_kind == "text" else "failed")
    if input_kind == "text":
        assert revoked["fallback"] is True
    assert gateway["calls"][-1][1] is False

    queued_id = await enqueue(3)
    monkeypatch.setattr(settings, "assisted_features_enabled", False)
    calls_before_pause = len(gateway["calls"])
    assert not await transcription_queue.process_next_transcription()
    queued = await session.get(TranscriptionJob, queued_id)
    assert queued.status == "queued" and queued.attempt_count == 0
    assert len(gateway["calls"]) == calls_before_pause
    # A pausa do provedor preserva o modo determinístico para novos diálogos.
    status, script = await _criar(client, headers, mode="script")
    assert status == 201
    response = await client.post(
        f"/api/speaking/dialogues/{script['id']}/turns/1/text",
        headers=headers,
        json={"text": STUDENT_TEXT, "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 202 and response.json()["state"] == "completed"
    assert len(gateway["calls"]) == calls_before_pause

    # Em produção os processos precisam ser recriados para recarregar settings.
    monkeypatch.setattr(settings, "assist_provider_token", NEW_TOKEN)
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    assert await transcription_queue.process_next_transcription()
    resumed = await turn(3)
    assert resumed["state"] == "completed" and not resumed["fallback"]
    assert resumed["partner_text"] == PARTNER_TEXT
    await session.refresh(queued)
    assert queued.attempt_count == 1
    calls_after_resume = len(gateway["calls"])
    assert not await transcription_queue.process_next_transcription()
    assert len(gateway["calls"]) == calls_after_resume

    # Indisponibilidade com token válido mantém a mesma degradação controlada.
    gateway["unavailable"] = True
    await enqueue(4)
    assert await transcription_queue.process_next_transcription()
    unavailable = await turn(4)
    assert unavailable["error_code"] == "provider_unavailable"
    assert unavailable["state"] == ("completed" if input_kind == "text" else "failed")
    assert gateway["calls"][-1][1] is True
    reservations = list((await session.scalars(select(AssistReservation))).all())
    assert len(reservations) == 4
    assert all(reservation.state == "consumed" for reservation in reservations)
    assert all(call[2] for call in gateway["calls"])

    records = [r for r in caplog.records if r.name.startswith("app.")]
    formatted = "\n".join(FormatadorJson().format(record) for record in records)
    assert "transcription_claimed" in formatted and "dialogue_job_completed" in formatted
    assert "app.request" in formatted
    for private in (
        OLD_TOKEN,
        NEW_TOKEN,
        STUDENT_TEXT,
        PARTNER_TEXT,
        ERROR_BODY,
        headers["Authorization"],
        f"sec48-{input_kind}@",
    ):
        assert private not in formatted
