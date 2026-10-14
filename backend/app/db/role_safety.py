"""Identidade mínima por processo; configuração explícita, sem elevar runtime/worker."""

from collections.abc import Sequence
from typing import Any, Literal

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

Purpose = Literal["runtime", "worker", "migrator"]
ROLE_SQL = """
SELECT current_user, session_user, r.rolsuper, r.rolcreatedb, r.rolcreaterole,
       r.rolreplication, r.rolbypassrls,
       has_database_privilege(current_user,current_database(),'CREATE'),
       has_schema_privilege(current_user,'public','CREATE'),
       pg_has_role(session_user,'aulas_owner','MEMBER')
FROM pg_roles r WHERE r.rolname=session_user
"""


def connect_args(purpose: Purpose | None) -> dict[str, Any]:
    return {"server_settings": {"role": "aulas_owner"}} if purpose == "migrator" else {}


def validate_identity(row: Sequence[object] | None, purpose: Purpose) -> None:
    expected = "aulas_owner" if purpose == "migrator" else f"aulas_{purpose}"
    if row is None or len(row) != 10 or tuple(row[:2]) != (expected, f"aulas_{purpose}"):
        raise RuntimeError("Identidade do papel SQL não corresponde ao processo.")
    if any(value is not False for value in row[2:7]):
        raise RuntimeError("Processo não pode usar privilégios administrativos globais.")
    if purpose != "migrator" and any(value is not False for value in row[7:]):
        raise RuntimeError("Runtime/worker não podem criar schema ou assumir seu proprietário.")


def guard_role_engine(engine: AsyncEngine, purpose: Purpose) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def check(connection: Any, record: Any) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute(ROLE_SQL)
            validate_identity(cursor.fetchone(), purpose)
        finally:
            cursor.close()
            connection.rollback()
