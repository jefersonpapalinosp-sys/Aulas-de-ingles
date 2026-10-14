"""Barreiras para impedir testes e migrations de teste sobre dados de estudo."""

from collections.abc import MutableMapping, Sequence
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine

TEST_DATABASE = "aulas_ingles_test"
TEST_ROLE = "aulas_test"
TEST_MARKER = "aulas-ingles:disposable-test:v1"
DEFAULT_TEST_URL = (
    "postgresql+asyncpg://aulas_test:aulas_test_only@127.0.0.1:55435/aulas_ingles_test"
)
IDENTITY_SQL = """
SELECT current_database(), current_user,
       shobj_description(d.oid, 'pg_database'),
       r.rolsuper, r.rolcreatedb, r.rolcreaterole
FROM pg_database d JOIN pg_roles r ON r.rolname = current_user
WHERE d.datname = current_database()
"""


class UnsafeTestDatabase(RuntimeError):
    """A execução é recusada antes de entregar a conexão ao chamador."""


def validate_test_target(database_url: str, app_env: str) -> None:
    if app_env != "test":
        raise UnsafeTestDatabase("Testes exigem APP_ENV=test; nenhuma conexão foi aberta.")
    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError):
        raise UnsafeTestDatabase("URL de teste inválida; credenciais não serão exibidas.") from None
    if (
        url.drivername != "postgresql+asyncpg"
        or url.database != TEST_DATABASE
        or url.username != TEST_ROLE
        or url.query
    ):
        raise UnsafeTestDatabase(
            "Alvo recusado: use o banco aulas_ingles_test e o papel aulas_test, "
            "sem parâmetros que alterem a conexão. Execute make test-db-up."
        )


def configure_test_environment(environ: MutableMapping[str, str]) -> str:
    """Não herda nem sobrescreve silenciosamente uma URL real exportada no shell."""
    target = environ.get("TEST_DATABASE_URL") or environ.get("DATABASE_URL") or DEFAULT_TEST_URL
    app_env = environ.get("APP_ENV", "test")
    validate_test_target(target, app_env)
    existing = environ.get("DATABASE_URL")
    if existing and existing != target:
        raise UnsafeTestDatabase(
            "DATABASE_URL e TEST_DATABASE_URL divergem. Remova a URL não destinada aos testes."
        )
    environ["DATABASE_URL"] = target
    environ["APP_ENV"] = "test"
    return target


def validate_test_identity(identity: Sequence[object] | None) -> None:
    if (
        identity is None
        or len(identity) != 6
        or tuple(identity[:3]) != (TEST_DATABASE, TEST_ROLE, TEST_MARKER)
        or any(value is not False for value in identity[3:])
    ):
        raise UnsafeTestDatabase(
            "Banco não é descartável ou papel tem privilégios administrativos. "
            "Nenhuma operação da suíte foi autorizada."
        )


def guard_test_engine(engine: AsyncEngine, database_url: str, app_env: str) -> None:
    """Verifica URL e identidade real de CADA conexão física antes de uso.

    O evento connect também atende conexões abertas pelo worker e pelo Alembic.
    Só uma leitura de metadados ocorre antes de a guarda aceitar o destino.
    """
    validate_test_target(database_url, app_env)

    @event.listens_for(engine.sync_engine, "connect")
    def verify_connection(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(IDENTITY_SQL)
            validate_test_identity(cursor.fetchone())
        finally:
            cursor.close()
            dbapi_connection.rollback()
