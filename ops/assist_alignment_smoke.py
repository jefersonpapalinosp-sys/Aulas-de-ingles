"""Smoke HTTP 39F sem provedores: clone dedicado ou DEV confirmado.

Executar pela imagem conferida ou dentro do container DEV confirmado pelo operador.
A conta sintética é removida por ID + e-mail exatos no finally. Sequências podem
avançar; dados históricos não mudam. Estudo exige --study-live e runtime limitado.
Nunca usar fixtures de pytest contra esses bancos.
"""

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import OpenerDirector, ProxyHandler, Request, build_opener
from uuid import uuid4


def validate_environment(env: Mapping[str, str], live: bool, study: bool = False) -> None:
    parsed = urlsplit(env.get("DATABASE_URL", ""))
    allowed_hosts = {"db"} if live else {"assist-check-db", "dev39-check-db", "study39-check-db"}
    if (
        env.get("APP_ENV") != ("prod" if study else "dev")
        or (
            env.get("DATABASE_PURPOSE") != "runtime" if study else bool(env.get("DATABASE_PURPOSE"))
        )
        or (study and (not live or parsed.username != "aulas_runtime"))
        or parsed.scheme != "postgresql+asyncpg"
        or parsed.hostname not in allowed_hosts
        or parsed.port not in (None, 5432)
        or (not live and parsed.path != "/aulas_ingles_restore")
        or env.get("ASSISTED_FEATURES_ENABLED", "").lower() != "false"
    ):
        raise ValueError("Ambiente não autorizado para smoke.")


def request(
    opener: OpenerDirector,
    path: str,
    headers: Mapping[str, str] | None = None,
    body: object = None,
    method: str | None = None,
) -> tuple[int, Message, object]:
    req = Request(
        "http://127.0.0.1:8000" + path,
        headers={"Content-Type": "application/json", **(headers or {})},
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )
    try:
        response = opener.open(req, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, json.loads(response.read())


def json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Resposta deve ser um objeto JSON.")
    return dict(value)


def object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError("Resposta deve ser uma lista JSON.")
    return [json_object(item) for item in value]


async def smoke(live: bool = False, study: bool = False) -> None:
    validate_environment(os.environ, live, study)
    # Imports tardios: nenhum engine ou configuração de app antes da guarda.
    from app.core.security import criar_token
    from app.db.models import User
    from app.db.session import dispose_engine, get_engine
    from app.services import assist_quota
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import AsyncSession

    checks = 0
    opener = build_opener(ProxyHandler({}))

    email = f"align39f-{uuid4().hex}@example.invalid"
    user_id = None
    engine = get_engine()
    try:
        async with engine.connect() as connection:
            try:
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    user = User(
                        email=email,
                        password_hash="!no-password-login",
                        display_name="Smoke 39F",
                    )
                    session.add(user)
                    await session.flush()
                    user_id = user.id
                    await session.commit()
                token, _ = criar_token(user_id, "access")
                headers = {"Authorization": f"Bearer {token}"}
                code, _, _ = request(opener, "/api/assist/status")
                assert code == 401
                checks += 1
                for path in (
                    "/api/assist/status",
                    "/api/writing/history",
                    "/api/speaking/attempts",
                ):
                    code, response_headers, _ = request(opener, path, headers)
                    assert code == 200 and "no-store" in response_headers["cache-control"]
                    checks += 1
                code, _, body = request(opener, "/api/lessons/31")
                assert code == 200
                prompt = object_list(json_object(body)["writing_prompts"])[0]["id"]
                assert isinstance(prompt, int) and not isinstance(prompt, bool) and prompt > 0
                checks += 1
                code, _, body = request(
                    opener,
                    f"/api/writing/prompts/{prompt}/draft",
                    headers,
                    {
                        "text": "The train is faster than the bus. We should take it.",
                        "expected_revision": 0,
                    },
                    method="PUT",
                )
                assert code == 200 and json_object(body)["revision"] == 1
                checks += 1
                code, _, body = request(
                    opener,
                    f"/api/writing/prompts/{prompt}/feedback",
                    headers,
                    {
                        "text": "The train is faster than the bus. We should take it.",
                        "assisted": False,
                    },
                )
                assert code == 200 and json_object(body)["analysis_mode"] == "deterministic"
                checks += 1
                code, _, body = request(opener, "/api/writing/history", headers)
                assert code == 200 and len(object_list(body)) == 1
                checks += 1
                code, _, body = request(opener, "/api/assist/status", headers)
                assert code == 200 and json_object(body)["used_today"] == 0
                checks += 1
                # Exercita o ledger diretamente, sem despachar a nenhum provedor.
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    reservation, fresh = await assist_quota.reserve(
                        session, user_id, str(uuid4()), "0" * 64, "writing"
                    )
                    assert fresh
                    reservation_id = reservation.id
                    await session.commit()
                code, _, balance = request(opener, "/api/assist/status", headers)
                assert code == 200 and json_object(balance)["reserved_today"] == 1
                checks += 1
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    assert await assist_quota.consume(session, reservation_id)
                    await assist_quota.record_cost(session, reservation_id, 0)
                    await session.commit()
                code, _, balance = request(opener, "/api/assist/status", headers)
                assert code == 200 and json_object(balance)["consumed_today"] == 1
                assert (
                    json_object(balance)["reserved_today"] == 0
                    and not json_object(balance)["cost_incomplete"]
                )
                checks += 1
            finally:
                if user_id is not None:
                    # Somente esta conta, nunca DELETE amplo nem limpeza por prefixo.
                    async with AsyncSession(bind=connection) as session:
                        removed = await session.execute(
                            delete(User)
                            .where(User.id == user_id, User.email == email)
                            .returning(User.id)
                        )
                        assert removed.scalar_one() == user_id
                        await session.commit()
                async with AsyncSession(bind=connection) as session:
                    assert (
                        await session.execute(select(User.id).where(User.email == email))
                    ).first() is None
    finally:
        await dispose_engine()
    print(
        json.dumps(
            {
                "verified": True,
                "mode": "http-study" if study else "http-dev" if live else "http-clone",
                "checks": checks,
                "synthetic_user_remaining": 0,
                "provider_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    try:
        asyncio.run(
            smoke(
                live=bool({"--live", "--study-live"} & set(sys.argv[1:])),
                study="--study-live" in sys.argv[1:],
            )
        )
    except Exception as error:
        # Somente tipo e linha: nunca corpo HTTP, tokens, SQL ou parâmetros.
        trace = error.__traceback__
        while trace is not None and trace.tb_next is not None:
            trace = trace.tb_next
        line = trace.tb_lineno if trace else 0
        print(
            f"Smoke 39F não aprovado: {type(error).__name__}, linha {line}.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
