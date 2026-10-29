"""Sonda SEC-49 dentro do container descartável; sem argumentos de alvo/segredo."""

import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.role_safety import ROLE_SQL, Purpose, validate_identity
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from ops.recovery_archive import require
from ops.rotation_provider import rehearse_provider

DATABASE = "aulas_rotation_lab"
ADMIN = "aulas_rotation_admin"
MARKER = "aulas-ingles:rotation49:v1"
ROLES = ("aulas_backup", "aulas_migrator", "aulas_worker", "aulas_runtime")
PURPOSES: dict[str, Purpose] = {
    "aulas_runtime": "runtime",
    "aulas_worker": "worker",
    "aulas_migrator": "migrator",
}
ROLE_MARKER = "aulas-ingles:rotation49-role:v1"
STAGE = "preflight"
EXPECTED = {
    "verified": True,
    "jwt_old_access_status": 401,
    "jwt_old_refresh_status": 401,
    "jwt_login_status": 200,
    "jwt_new_refresh_status": 200,
    "mixed_old_key_status": 200,
    "mixed_new_key_status": 401,
    "database_roles": 4,
    "old_connections_survived": 4,
    "old_passwords_rejected": 4,
    "new_passwords_accepted": 4,
    "runtime_stale_health": 503,
    "runtime_rotated_health": 200,
    "database_session_survived": True,
    "grants_preserved": True,
    "synthetic_note_preserved": True,
    "auth_bucket_explicit_preserved": True,
    "provider_calls": 5,
    "provider_overlap_ok": True,
    "provider_old_revoked": True,
    "provider_new_ok": True,
    "synthetic_users_remaining": 0,
}
TIMINGS = {"jwt_ms", "password_ms", "provider_ms", "total_ms"}


def validate_report(value: object) -> dict[str, int | bool]:
    require(isinstance(value, dict), "Recibo de rotação inválido.")
    assert isinstance(value, dict)
    require(set(value) == set(EXPECTED) | TIMINGS, "Campos inesperados no recibo de rotação.")
    result: dict[str, int | bool] = {}
    for key, expected in EXPECTED.items():
        actual = value[key]
        require(
            type(actual) is type(expected) and actual == expected, "Prova de rotação incompleta."
        )
        result[key] = actual
    for key in TIMINGS:
        elapsed = value[key]
        require(type(elapsed) is int and 0 <= elapsed <= 300_000, "Duração inválida.")
        result[key] = elapsed
    return result


def url(role: str, password: str) -> str:
    require(role in (*ROLES, ADMIN), "Papel fora do laboratório.")
    require(
        len(password) >= 24 and all(c.isalnum() or c == "_" for c in password),
        "Formato de credencial sintética inválido.",
    )
    return f"postgresql+asyncpg://{role}:{password}@db:5432/{DATABASE}"


def engine(role: str, password: str) -> AsyncEngine:
    return create_async_engine(
        url(role, password), hide_parameters=True, pool_size=1, max_overflow=0
    )


async def script(connection: AsyncConnection, sql: str) -> None:
    raw = await connection.get_raw_connection()
    driver = raw.driver_connection
    require(driver is not None, "Conexão administrativa ausente.")
    assert driver is not None
    await driver.execute(sql)


async def prepare(admin: AsyncConnection, passwords: dict[str, str]) -> None:
    identity = (
        await admin.execute(
            text(
                "SELECT current_database(),current_user,shobj_description(oid,'pg_database') "
                "FROM pg_database WHERE datname=current_database()"
            )
        )
    ).one()
    require(tuple(identity) == (DATABASE, ADMIN, MARKER), "Identidade SEC-49 não confirmada.")
    # Reexecução nunca apaga um cenário anterior incompleto.
    if await admin.scalar(text("SELECT to_regclass('public.app_user')")):
        require(
            await admin.scalar(text("SELECT count(*) FROM app_user")) == 0,
            "Laboratório ocupado; preservar dados para diagnóstico.",
        )
    for role in ("aulas_owner", *ROLES):
        marker = await admin.scalar(
            text("SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=:role"),
            {"role": role},
        )
        exists = await admin.scalar(
            text("SELECT count(*) FROM pg_roles WHERE rolname=:role"), {"role": role}
        )
        require(not exists or marker == ROLE_MARKER, "Papel existente sem marcador SEC-49.")
        if not exists:
            access = "NOLOGIN" if role == "aulas_owner" else "LOGIN"
            await script(
                admin,
                f"CREATE ROLE {role} {access} NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION NOBYPASSRLS",
            )
            await script(admin, f"COMMENT ON ROLE {role} IS '{ROLE_MARKER}'")
        if role in passwords:
            await script(admin, f"ALTER ROLE {role} PASSWORD '{passwords[role]}'")
    await script(
        admin,
        f"""
        REVOKE ALL ON DATABASE {DATABASE} FROM PUBLIC;
        GRANT CONNECT ON DATABASE {DATABASE} TO aulas_owner,{",".join(ROLES)};
        GRANT aulas_owner TO aulas_migrator WITH ADMIN FALSE;
        REVOKE CREATE ON SCHEMA public FROM PUBLIC;
        ALTER SCHEMA public OWNER TO aulas_owner;
    """,
    )
    env = {
        **os.environ,
        "APP_ENV": "dev",
        "DATABASE_PURPOSE": "migrator",
        "DATABASE_URL": url("aulas_migrator", passwords["aulas_migrator"]),
    }
    for args in (("alembic", "upgrade", "head"), ("app.cli", "seed")):
        subprocess.run(
            [sys.executable, "-m", *args],
            env=env,
            check=True,
            timeout=90,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    await script(admin, Path(__file__).with_name("roles_policy.sql").read_text())


@dataclass
class Response:
    status: int
    data: dict[str, Any]
    refresh: str | None


def request(
    port: int,
    path: str,
    *,
    body: object = None,
    token: str | None = None,
    refresh: str | None = None,
) -> Response:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if refresh:
        headers["Cookie"] = f"refresh_token={refresh}"
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api{path}",
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        result = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as error:
        result = error
    with result:
        payload: object = json.load(result)
        require(isinstance(payload, dict), "Resposta HTTP inesperada.")
        assert isinstance(payload, dict)
        cookie = SimpleCookie()
        cookie.load(result.headers.get("Set-Cookie", ""))
        value = cookie.get("refresh_token")
        return Response(result.status, payload, value.value if value else None)


class API:
    def __init__(self, env: dict[str, str], port: int = 8000) -> None:
        self.port = port
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                require(self.process.poll() is None, "API sintética encerrou antes do readiness.")
                try:
                    if request(port, "/live").status == 200:
                        return
                except (urllib.error.URLError, TimeoutError):
                    pass
                time.sleep(0.1)
            raise RuntimeError("API sintética não iniciou.")
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def milliseconds(start: float) -> int:
    return round((time.monotonic() - start) * 1000)


async def permissions(admin: AsyncConnection) -> list[tuple[object, ...]]:
    rows = await admin.execute(
        text("""
        SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,
          rolcanlogin,pg_has_role(rolname,'aulas_owner','MEMBER')
        FROM pg_roles WHERE rolname LIKE 'aulas_%' ORDER BY rolname
    """)
    )
    grants = await admin.execute(
        text("""
        SELECT grantee,table_name,privilege_type FROM information_schema.role_table_grants
        WHERE table_schema='public' ORDER BY grantee,table_name,privilege_type
    """)
    )
    return [tuple(row) for row in rows] + [tuple(row) for row in grants]


async def rotate_passwords(
    admin: AsyncConnection, old: dict[str, str], new: dict[str, str], report: dict[str, int | bool]
) -> None:
    for role in ROLES:
        old_engine = engine(role, old[role])
        new_engine = engine(role, new[role])
        try:
            async with old_engine.connect() as established:
                await established.execute(text("SELECT 1"))
                await script(admin, f"ALTER ROLE {role} PASSWORD '{new[role]}'")
                require(
                    await established.scalar(text("SELECT 1")) == 1, "Sessão ativa interrompida."
                )
                report["old_connections_survived"] += 1
                # Engine diferente: não reutilizar a conexão autenticada antes da troca.
                rejected_engine = engine(role, old[role])
                try:
                    try:
                        async with rejected_engine.connect():
                            raise RuntimeError("Senha antiga ainda aceita em conexão nova.")
                    except DBAPIError as error:
                        require(
                            getattr(error.orig, "sqlstate", None) == "28P01",
                            "Recusa não foi por senha inválida.",
                        )
                        report["old_passwords_rejected"] += 1
                finally:
                    await rejected_engine.dispose()
                async with new_engine.connect() as fresh:
                    purpose = PURPOSES.get(role)
                    if purpose == "migrator":
                        await fresh.execute(text("SET ROLE aulas_owner"))
                    if purpose is not None:
                        validate_identity((await fresh.execute(text(ROLE_SQL))).one(), purpose)
                    else:
                        require(
                            await fresh.scalar(text("SELECT count(*) FROM lesson")) == 82,
                            "Backup perdeu leitura do catálogo.",
                        )
                    report["new_passwords_accepted"] += 1
        finally:
            await old_engine.dispose()
            await new_engine.dispose()


async def run() -> dict[str, int | bool]:
    global STAGE
    require(
        os.environ.get("ROTATION_LAB") == "disposable-rotation49"
        and os.environ.get("APP_ENV") == "dev",
        "Sonda exclusiva do laboratório SEC-49.",
    )
    started = time.monotonic()
    old = {role: secrets.token_hex(32) for role in ROLES}
    new = {role: secrets.token_hex(32) for role in ROLES}
    jwt_old, jwt_new, bucket_key = (secrets.token_hex(32) for _ in range(3))
    admin_engine = engine(ADMIN, "rotation_disposable_only")
    report: dict[str, int | bool] = {
        "database_roles": len(ROLES),
        "old_connections_survived": 0,
        "old_passwords_rejected": 0,
        "new_passwords_accepted": 0,
    }
    servers: list[API] = []
    user_id: int | None = None
    email = f"rotation49-{uuid4().hex}@example.com"
    try:
        async with admin_engine.connect() as admin:
            admin = await admin.execution_options(isolation_level="AUTOCOMMIT")
            STAGE = "prepare"
            await prepare(admin, old)
            grants = await permissions(admin)
            env = {
                **os.environ,
                "APP_ENV": "dev",
                "DEPLOYMENT_PROFILE": "local",
                "DATABASE_PURPOSE": "runtime",
                "DATABASE_URL": url("aulas_runtime", old["aulas_runtime"]),
                "JWT_SECRET": jwt_old,
                "AUTH_BUCKET_SECRET": bucket_key,
                "ASSISTED_FEATURES_ENABLED": "false",
                "DIALOGUE_PRACTICE_ENABLED": "false",
            }
            STAGE = "initial_session"
            api = API(env)
            servers.append(api)
            login_body = {
                "email": email,
                "password": secrets.token_hex(16),
                "display_name": "Rotation lab",
            }
            registration = request(8000, "/auth/register", body=login_body)
            require(registration.status == 201, "Conta sintética não criada.")
            token = str(registration.data["access_token"])
            me = request(8000, "/auth/me", token=token)
            require(me.status == 200, "Sessão inicial recusada.")
            user_id = int(me.data["id"])
            initial_refresh = request(8000, "/auth/refresh", body={}, refresh=registration.refresh)
            require(
                initial_refresh.status == 200 and initial_refresh.refresh,
                "Refresh inicial recusado.",
            )
            token = str(initial_refresh.data["access_token"])
            await admin.execute(
                text(
                    "INSERT INTO notebook_entry(user_id,lesson_id,kind,content) "
                    "VALUES (:user,(SELECT min(id) FROM lesson),"
                    "'note','Synthetic rotation evidence')"
                ),
                {"user": user_id},
            )
            keys = set((await admin.execute(text("SELECT key FROM auth_rate_bucket"))).scalars())
            before = (
                (
                    await admin.execute(
                        text("SELECT content FROM notebook_entry WHERE user_id=:user"),
                        {"user": user_id},
                    )
                )
                .scalars()
                .all()
            )
            password_start = time.monotonic()
            require(before == ["Synthetic rotation evidence"], "Nota sintética não foi persistida.")
            STAGE = "password_rotation"
            await rotate_passwords(admin, old, new, report)
            require(
                request(8000, "/auth/me", token=token).status == 200, "Pool ativo perdeu sessão."
            )
            STAGE = "stale_consumer"
            stale = API(env, 8001)
            servers.append(stale)
            report["runtime_stale_health"] = request(8001, "/health").status
            stale.close()
            servers.remove(stale)
            api.close()
            servers.remove(api)
            env["DATABASE_URL"] = url("aulas_runtime", new["aulas_runtime"])
            api = API(env)
            servers.append(api)
            report["runtime_rotated_health"] = request(8000, "/health").status
            report["database_session_survived"] = (
                request(8000, "/auth/me", token=token).status == 200
            )
            report["password_ms"] = milliseconds(password_start)
            STAGE = "jwt_rotation"
            jwt_start = time.monotonic()
            env["JWT_SECRET"] = jwt_new
            updated = API(env, 8001)
            servers.append(updated)
            report["mixed_old_key_status"] = request(8000, "/auth/me", token=token).status
            report["mixed_new_key_status"] = request(8001, "/auth/me", token=token).status
            api.close()
            servers.remove(api)
            report["jwt_old_access_status"] = request(8001, "/auth/me", token=token).status
            report["jwt_old_refresh_status"] = request(
                8001, "/auth/refresh", body={}, refresh=initial_refresh.refresh
            ).status
            login = request(
                8001, "/auth/login", body={"email": email, "password": login_body["password"]}
            )
            report["jwt_login_status"] = login.status
            renewed = request(8001, "/auth/refresh", body={}, refresh=login.refresh)
            report["jwt_new_refresh_status"] = renewed.status
            require(
                request(8001, "/auth/me", token=str(renewed.data["access_token"])).status == 200,
                "Sessão nova não funciona após rotação JWT.",
            )
            report["jwt_ms"] = milliseconds(jwt_start)
            report["auth_bucket_explicit_preserved"] = keys == set(
                (await admin.execute(text("SELECT key FROM auth_rate_bucket"))).scalars()
            )
            report["synthetic_note_preserved"] = (
                before
                == (
                    await admin.execute(
                        text("SELECT content FROM notebook_entry WHERE user_id=:user"),
                        {"user": user_id},
                    )
                )
                .scalars()
                .all()
            )
            report["grants_preserved"] = grants == await permissions(admin)
            STAGE = "provider_rotation"
            provider_start = time.monotonic()
            for key, value in rehearse_provider().items():
                report[f"provider_{key}"] = value
            report["provider_ms"] = milliseconds(provider_start)
    finally:
        for server in servers:
            server.close()
        if user_id is not None:
            async with admin_engine.begin() as admin:
                await admin.execute(
                    text("DELETE FROM app_user WHERE id=:user AND email=:email"),
                    {"user": user_id, "email": email},
                )
        await admin_engine.dispose()
    # Leitura final com conexão nova depois do cleanup, sem declarar sucesso antes.
    check = engine(ADMIN, "rotation_disposable_only")
    try:
        async with check.connect() as admin:
            report["synthetic_users_remaining"] = int(
                await admin.scalar(text("SELECT count(*) FROM app_user"))
            )
    finally:
        await check.dispose()
    report["verified"] = True
    report["total_ms"] = milliseconds(started)
    return validate_report(report)


if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(run()), sort_keys=True))
    except Exception as error:
        # Somente fase fixa/tipo; nunca mensagem, payload, SQL ou DSN da exceção.
        print(f"SEC-49: fase={STAGE}; tipo={type(error).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
