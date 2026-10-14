"""Guardas sem banco e uma confirmação na base exclusivamente descartável."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import testing
from app.db import session as db_session
from app.db import test_safety
from app.db.test_safety import (
    DEFAULT_TEST_URL,
    IDENTITY_SQL,
    TEST_DATABASE,
    TEST_MARKER,
    TEST_ROLE,
    UnsafeTestDatabase,
    configure_test_environment,
    guard_test_engine,
    validate_test_identity,
    validate_test_target,
)

IDENTITY = (TEST_DATABASE, TEST_ROLE, TEST_MARKER, False, False, False)


def test_default_e_exclusivo_e_nao_depende_do_banco_de_estudo() -> None:
    environ: dict[str, str] = {}
    assert configure_test_environment(environ) == DEFAULT_TEST_URL
    assert environ == {"DATABASE_URL": DEFAULT_TEST_URL, "APP_ENV": "test"}


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://aulas:secret@localhost:5433/aulas_ingles",
        "postgresql+asyncpg://aulas:secret@localhost:5434/aulas_ingles",
        DEFAULT_TEST_URL.replace(TEST_ROLE + ":", "postgres:"),
        DEFAULT_TEST_URL.replace(TEST_DATABASE, "postgres"),
        DEFAULT_TEST_URL.replace(TEST_DATABASE, "aulas_test_sentinel"),
        DEFAULT_TEST_URL.replace("+asyncpg", ""),
        DEFAULT_TEST_URL + "?database=aulas_ingles",
        DEFAULT_TEST_URL + "?user=postgres",
        "secret-url-malformed",
        DEFAULT_TEST_URL.replace("55435", "secret-invalid-port"),
    ],
)
def test_recusa_alvo_inseguro_sem_exibir_url_ou_credencial(url: str) -> None:
    with pytest.raises(UnsafeTestDatabase) as error:
        validate_test_target(url, "test")
    assert "secret" not in str(error.value)
    assert url not in str(error.value)


@pytest.mark.parametrize("app_env", ["dev", "prod", "", "TEST"])
def test_nao_aceita_ambiente_ambiguo(app_env: str) -> None:
    with pytest.raises(UnsafeTestDatabase, match="APP_ENV=test"):
        validate_test_target(DEFAULT_TEST_URL, app_env)


def test_pode_escolher_outro_host_mas_identidade_ainda_sera_verificada() -> None:
    url = DEFAULT_TEST_URL.replace("127.0.0.1:55435", "test-db:5432")
    environ = {"TEST_DATABASE_URL": url}
    assert configure_test_environment(environ) == url
    assert environ["DATABASE_URL"] == url


@pytest.mark.parametrize(
    "environ",
    [
        {"DATABASE_URL": "postgresql+asyncpg://aulas:secret@localhost/aulas_ingles"},
        {"APP_ENV": "prod"},
        {"TEST_DATABASE_URL": DEFAULT_TEST_URL, "DATABASE_URL": "real-url"},
    ],
)
def test_nao_sobrescreve_configuracao_insegura(environ: dict[str, str]) -> None:
    before = environ.copy()
    with pytest.raises(UnsafeTestDatabase):
        configure_test_environment(environ)
    assert environ == before


def test_aceita_configuracao_explicita_coerente() -> None:
    environ = {"DATABASE_URL": DEFAULT_TEST_URL, "TEST_DATABASE_URL": DEFAULT_TEST_URL}
    assert configure_test_environment(environ) == DEFAULT_TEST_URL


@pytest.mark.parametrize(
    "identity",
    [
        None,
        (),
        ("aulas_ingles", *IDENTITY[1:]),
        (TEST_DATABASE, "postgres", *IDENTITY[2:]),
        (TEST_DATABASE, TEST_ROLE, None, False, False, False),
        (TEST_DATABASE, TEST_ROLE, "unmarked", False, False, False),
        (*IDENTITY[:3], True, False, False),
        (*IDENTITY[:3], False, True, False),
        (*IDENTITY[:3], False, False, True),
        (*IDENTITY[:3], None, False, False),
    ],
)
def test_recusa_identidade_real_diferente_ou_administrativa(identity) -> None:
    with pytest.raises(UnsafeTestDatabase):
        validate_test_identity(identity)


def test_aceita_marcador_e_papel_limitado() -> None:
    validate_test_identity(IDENTITY)


@pytest.mark.parametrize("identity", [IDENTITY, (*IDENTITY[:3], True, False, False)])
def test_conexao_e_verificada_antes_do_uso_e_leitura_e_encerrada(
    monkeypatch: pytest.MonkeyPatch, identity
) -> None:
    register = MagicMock(side_effect=lambda callback: callback)
    listens_for = MagicMock(return_value=register)
    monkeypatch.setattr(test_safety.event, "listens_for", listens_for)
    engine = MagicMock()
    guard_test_engine(engine, DEFAULT_TEST_URL, "test")
    listens_for.assert_called_once_with(engine.sync_engine, "connect")
    callback = register.call_args.args[0]
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = identity
    if identity == IDENTITY:
        callback(connection, None)
    else:
        with pytest.raises(UnsafeTestDatabase):
            callback(connection, None)
    cursor.execute.assert_called_once_with(IDENTITY_SQL)
    cursor.close.assert_called_once()
    connection.rollback.assert_called_once()


def test_engine_recusa_url_antes_de_criar_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = MagicMock(app_env="test", database_url="postgresql+asyncpg://aulas@db/aulas_ingles")
    factory = MagicMock()
    monkeypatch.setattr(db_session, "_engine", None)
    monkeypatch.setattr(db_session, "get_settings", lambda: settings)
    monkeypatch.setattr(db_session, "create_async_engine", factory)
    with pytest.raises(UnsafeTestDatabase):
        db_session.get_engine()
    factory.assert_not_called()


@pytest.mark.parametrize("command", ["check", "prepare", "invalid"])
def test_cli_so_prepara_apos_validar(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    check = AsyncMock()
    run = MagicMock()
    monkeypatch.setattr(testing, "check_database", check)
    monkeypatch.setattr(testing.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["app.testing", command])
    if command == "invalid":
        with pytest.raises(SystemExit) as error:
            testing.main()
        assert error.value.code == 2
        assert "uso:" in capsys.readouterr().err
    else:
        testing.main()
    check.assert_awaited_once()
    if command == "prepare":
        assert run.call_count == 2
        assert run.call_args_list[0].args[0] == [sys.executable, "-m", "alembic", "upgrade", "head"]
        assert run.call_args_list[1].args[0] == [sys.executable, "-m", "app.cli", "seed"]
        assert all(call.kwargs == {"check": True} for call in run.call_args_list)
    else:
        run.assert_not_called()


def test_cli_nao_conecta_nem_migra_com_url_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://aulas@db/aulas_ingles")
    check = AsyncMock()
    run = MagicMock()
    monkeypatch.setattr(testing, "check_database", check)
    monkeypatch.setattr(testing.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["app.testing", "prepare"])
    with pytest.raises(SystemExit) as error:
        testing.main()
    assert error.value.code == 2
    check.assert_not_called()
    run.assert_not_called()


@pytest.mark.parametrize("failure", [ConnectionError(), UnsafeTestDatabase("marcador ausente")])
def test_cli_nao_migra_sem_confirmar_identidade(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    monkeypatch.setattr(testing, "check_database", AsyncMock(side_effect=failure))
    run = MagicMock()
    monkeypatch.setattr(testing.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["app.testing", "prepare"])
    with pytest.raises(SystemExit) as error:
        testing.main()
    assert error.value.code == 2
    run.assert_not_called()


async def test_preflight_descarta_engine_mesmo_quando_banco_recusa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock()
    connection = AsyncMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    dispose = AsyncMock()
    monkeypatch.setattr(db_session, "get_engine", lambda: engine)
    monkeypatch.setattr(db_session, "dispose_engine", dispose)
    await testing.check_database()
    dispose.assert_awaited_once()
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"
    dispose.reset_mock()
    engine.connect.return_value.__aenter__.side_effect = UnsafeTestDatabase("recusado")
    with pytest.raises(UnsafeTestDatabase):
        await testing.check_database()
    dispose.assert_awaited_once()


async def test_integracao_base_tem_marcador_e_nao_acessa_sentinela(session: AsyncSession) -> None:
    identity = (await session.execute(text(IDENTITY_SQL))).one()
    validate_test_identity(identity)
    can_connect = await session.scalar(
        text("SELECT has_database_privilege(current_user, 'aulas_test_sentinel', 'CONNECT')")
    )
    assert can_connect is False
    assert os.environ["APP_ENV"] == "test"
