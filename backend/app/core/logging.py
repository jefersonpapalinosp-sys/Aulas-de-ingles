"""Log estruturado em JSON, com request-id.

Uma linha por evento, em JSON, porque log de container vira texto num
agregador e grep em texto livre não sobrevive a um incidente. O `request_id`
amarra todas as linhas de uma mesma requisição — inclusive o traceback.
"""

import json
import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from fastapi import Request, Response

# ContextVar e não atributo de request: o logger lá embaixo, dentro de um
# serviço, não recebe o request e ainda assim precisa marcar a linha.
request_id_atual: ContextVar[str] = ContextVar("request_id", default="-")

CABECALHO = "X-Request-ID"

_PADRAO = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class FormatadorJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        evento: dict[str, object] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_atual.get(),
        }
        # Campos passados em `extra=` entram no JSON em vez de sumirem.
        for chave, valor in record.__dict__.items():
            if chave not in _PADRAO and not chave.startswith("_"):
                evento[chave] = valor
        if record.exc_info:
            evento["exception"] = self.formatException(record.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


def configurar(nivel: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(FormatadorJson())
    raiz = logging.getLogger()
    raiz.handlers = [handler]
    raiz.setLevel(nivel.upper())
    # O access log do uvicorn repete o que o middleware já registra, com
    # menos informação e sem o request-id.
    logging.getLogger("uvicorn.access").disabled = True


async def middleware_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Dá um id a cada requisição e registra uma linha com a latência.

    Um id vindo de fora é respeitado: num futuro com proxy na frente, é ele
    que amarra o rastro de ponta a ponta.
    """
    rid = request.headers.get(CABECALHO) or uuid.uuid4().hex[:16]
    token = request_id_atual.set(rid)
    comeco = time.perf_counter()
    try:
        resposta = await call_next(request)
    except Exception:
        logging.getLogger("app.request").exception(
            "requisição falhou",
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round((time.perf_counter() - comeco) * 1000, 2),
            },
        )
        request_id_atual.reset(token)
        raise

    duracao = round((time.perf_counter() - comeco) * 1000, 2)
    logging.getLogger("app.request").info(
        "%s %s %s",
        request.method,
        request.url.path,
        resposta.status_code,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": resposta.status_code,
            "duration_ms": duracao,
        },
    )
    resposta.headers[CABECALHO] = rid
    request_id_atual.reset(token)
    return resposta
