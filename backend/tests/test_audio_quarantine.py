import hashlib
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from app.services.audio_audit import inventory
from app.services.audio_quarantine import Quarantine, QuarantineRefused

KEY = "a" * 32 + ".wav"
OP = "b" * 32
DATA = b"synthetic private voice"
SHA = hashlib.sha256(DATA).hexdigest()
DATABASE = "aulas_ingles_test"


def audio(root, key=KEY, data=DATA):
    file = root / key
    file.write_bytes(data)
    file.chmod(0o600)
    return file


def future():
    # Apenas fixtures: produção usa clock_timestamp() do banco, sem override de idade.
    return datetime.now(UTC) + timedelta(days=2)


def prepare(storage):
    return storage.prepare(KEY, SHA, OP, future())


@pytest.mark.timezone
def test_round_trip_and_idempotent_resume_preserve_bytes_permissions_and_journal(tmp_path):
    audio(tmp_path)
    with Quarantine(tmp_path, DATABASE) as storage:
        record = prepare(storage)
        result = storage.finish(record)
        assert result["state"] == "quarantined" and not result["deleted"]
        assert storage.finish(storage.load(OP)) == result
        assert not (tmp_path / KEY).exists()
        assert (tmp_path / ".quarantine" / OP / "audio").read_bytes() == DATA
        restored = storage.finish(record, restore=True)
        assert restored["state"] == "restored"
        assert storage.finish(record) == restored  # Intenção de restore é durável.
    assert (tmp_path / KEY).read_bytes() == DATA
    assert (tmp_path / KEY).stat().st_mode & 0o777 == 0o600
    assert (tmp_path / ".quarantine" / OP / "record.json").is_file()
    report = inventory(tmp_path, [], future())
    assert report["counts"]["quarantine_directory_protected"] == 1


@pytest.mark.parametrize(
    "phase", ["journal", "link", "unlink", "restore_journal", "restore_link", "restore_unlink"]
)
def test_real_process_crash_resumes_without_losing_audio(tmp_path, phase):
    audio(tmp_path)
    code = """
import os, sys
from pathlib import Path
from datetime import datetime, UTC, timedelta
from app.services.audio_quarantine import Quarantine
root, database, key, digest, operation, phase = sys.argv[1:]
with Quarantine(Path(root), database) as storage:
    record = storage.prepare(key, digest, operation, datetime.now(UTC) + timedelta(days=2))
    if phase == "journal": os._exit(73)
    if phase.startswith("restore_"): storage.finish(record)
    if phase == "restore_journal":
        original = storage._write
        def write(*args):
            original(*args)
            os._exit(73)
        storage._write = write
    else:
        name = "link" if phase.endswith("link") and not phase.endswith("unlink") else "unlink"
        original = getattr(os, name)
        def mutate(*args, **kwargs):
            original(*args, **kwargs)
            os._exit(73)
        setattr(os, name, mutate)
    storage.finish(record, restore=phase.startswith("restore_"))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path), DATABASE, KEY, SHA, OP, phase],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 73, result.stderr.decode()
    with Quarantine(tmp_path, DATABASE) as storage:
        record = storage.load(OP)
        result = storage.finish(record)
        assert result["state"] == ("restored" if phase.startswith("restore_") else "quarantined")
        storage.finish(record, restore=True)
    assert (tmp_path / KEY).read_bytes() == DATA


@pytest.mark.timezone
@pytest.mark.parametrize(
    "case",
    [
        "recent",
        "checksum",
        "symlink",
        "hardlink",
        "large",
        "public",
        "temporary",
        "unknown",
        "traversal",
        "missing",
    ],
)
def test_protected_candidates_never_get_journal_or_move(tmp_path, case):
    file = audio(tmp_path)
    key, digest, now = KEY, SHA, future()
    if case == "recent":
        now = datetime.now(UTC)
    elif case == "checksum":
        digest = "0" * 64
    elif case == "symlink":
        file.rename(tmp_path / "original")
        file.symlink_to(tmp_path / "original")
    elif case == "hardlink":
        os.link(file, tmp_path / "other")
    elif case == "large":
        file.write_bytes(b"0" * 2_000_001)
    elif case == "public":
        file.chmod(0o644)
    elif case in {"temporary", "unknown", "traversal", "missing"}:
        key = {
            "temporary": KEY + ".tmp",
            "unknown": "voice.wav",
            "traversal": "../" + KEY,
            "missing": "c" * 32 + ".wav",
        }[case]
    with Quarantine(tmp_path, DATABASE) as storage, pytest.raises((QuarantineRefused, OSError)):
        storage.prepare(key, digest, OP, now)
    assert file.exists() and not (tmp_path / ".quarantine").exists()


def test_unsafe_roots_and_concurrent_operator_are_refused(tmp_path):
    audio(tmp_path)
    with (
        Quarantine(tmp_path, DATABASE),
        pytest.raises(BlockingIOError),
        Quarantine(tmp_path, DATABASE),
    ):
        pass
    linked = tmp_path / "redirect"
    linked.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(QuarantineRefused), Quarantine(linked, DATABASE):
        pass
    tmp_path.chmod(0o777)
    with pytest.raises(QuarantineRefused), Quarantine(tmp_path, DATABASE):
        pass


@pytest.mark.timezone
@pytest.mark.parametrize(
    "case",
    ["changed", "other_destination", "journal", "database", "missing", "external_link", "budget"],
)
def test_recovery_refuses_conflicts_without_overwrite(tmp_path, case):
    file = audio(tmp_path)
    with Quarantine(tmp_path, DATABASE) as storage:
        record = prepare(storage)
        if case == "changed":
            file.write_bytes(b"different")
        elif case == "other_destination":
            storage.finish(record)
            audio(tmp_path, data=b"another recording")
        elif case == "journal":
            (tmp_path / ".quarantine" / OP / "record.json").write_text('{"key":"../outside"}')
        elif case == "database":
            storage.database = "another_database"
        elif case == "missing":
            file.unlink()
        elif case == "external_link":
            os.link(file, tmp_path / "external")
        else:
            storage.deadline = 0
        with pytest.raises(QuarantineRefused):
            storage.finish(storage.load(OP), restore=case == "other_destination")
    if case == "other_destination":
        assert file.read_bytes() == b"another recording"
        assert (tmp_path / ".quarantine" / OP / "audio").read_bytes() == DATA


@pytest.mark.timezone
def test_changed_after_prepare_and_during_move_preserves_source(tmp_path, monkeypatch):
    audio(tmp_path)
    with Quarantine(tmp_path, DATABASE) as storage:
        record = prepare(storage)
        # Simula observação anterior: chmod no mesmo tick não muda ctime em todo FS.
        record["source_ctime_ns"] -= 1
        with pytest.raises(QuarantineRefused, match="changed_after_prepare"):
            storage.finish(record)
    # Novo fixture/operação, sem reaproveitar seleção invalidada.
    other = tmp_path / "separate"
    other.mkdir(mode=0o700)
    audio(other)
    with Quarantine(other, DATABASE) as storage:
        record = prepare(storage)
        original = os.link

        def change(*args, **kwargs):
            original(*args, **kwargs)
            (other / KEY).write_bytes(b"x" * len(DATA))

        monkeypatch.setattr(os, "link", change)
        with pytest.raises(QuarantineRefused):
            storage.finish(record)
    assert (other / KEY).exists()  # Não remove origem cujo conteúdo mudou.


@pytest.mark.timezone
def test_journal_or_destination_link_cannot_redirect_storage(tmp_path):
    file = audio(tmp_path)
    (tmp_path / ".quarantine").symlink_to(tmp_path, target_is_directory=True)
    with Quarantine(tmp_path, DATABASE) as storage, pytest.raises(OSError):
        prepare(storage)
    assert file.read_bytes() == DATA


@pytest.mark.timezone
async def test_cli_checks_fresh_references_and_preserves_database(client, tmp_path, monkeypatch):
    from sqlalchemy import event, update

    from app import audio_quarantine as command
    from app.core.config import get_settings
    from app.db.models import SpeakingAttempt
    from app.db.session import get_engine, get_sessionmaker
    from tests.test_speaking import conta, cue_id

    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers = await conta(client, "quarantine-reference")
    response = await client.post(
        "/api/speaking/attempts",
        headers=headers,
        json={"cue_id": await cue_id(client), "duration_ms": 1000, "consent": True},
    )
    attempt_id = response.json()["id"]
    audio(tmp_path)
    with Quarantine(tmp_path, DATABASE) as storage:
        prepare(storage)  # Simula journal selecionado antes de referência nova.
    async with get_sessionmaker()() as session:
        await session.execute(
            update(SpeakingAttempt).where(SpeakingAttempt.id == attempt_id).values(storage_key=KEY)
        )
        await session.commit()
    args = dict(operation=OP, confirm_storage=str(tmp_path), confirm_database=DATABASE)
    with pytest.raises(QuarantineRefused, match="referenced_file_protected"):
        await command.execute(action="resume", **args)
    assert (tmp_path / KEY).exists()
    async with get_sessionmaker()() as session:
        await session.execute(
            update(SpeakingAttempt).where(SpeakingAttempt.id == attempt_id).values(storage_key=None)
        )
        await session.commit()
    engine = get_engine()
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        assert (await command.execute(action="resume", **args))["state"] == "quarantined"
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert not any(sql.startswith(("DELETE", "UPDATE", "INSERT")) for sql in statements)
    assert any("EXCLUSIVE MODE NOWAIT" in sql for sql in statements)
    assert (await command.execute(action="restore", **args))["state"] == "restored"
    assert (tmp_path / KEY).read_bytes() == DATA
    async with get_sessionmaker()() as session:
        attempt = await session.get(SpeakingAttempt, attempt_id)
        assert attempt.status == "pending" and attempt.storage_key is None


async def test_sql_lock_refuses_active_upload_before_filesystem_access(
    client, tmp_path, monkeypatch
):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from app import audio_quarantine as command
    from app.core.config import get_settings
    from app.db.session import get_sessionmaker

    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    audio(tmp_path)
    async with get_sessionmaker()() as session:
        # Mesmo modo obtido pelo SELECT FOR UPDATE da API antes de salvar bytes.
        await session.execute(text("LOCK TABLE speaking_attempt IN ROW SHARE MODE"))
        with pytest.raises(DBAPIError):
            await command.execute(
                action="quarantine",
                operation=OP,
                key=KEY,
                digest=SHA,
                confirm_storage=str(tmp_path),
                confirm_database=DATABASE,
            )
        await session.rollback()
    assert not (tmp_path / ".quarantine").exists()


@pytest.mark.timezone
async def test_command_quarantine_uses_server_time_and_explicit_confirmation(
    client, tmp_path, monkeypatch
):
    from app import audio_quarantine as command
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    audio(tmp_path)
    args = dict(
        action="quarantine",
        operation=OP,
        key=KEY,
        digest=SHA,
        confirm_storage=str(tmp_path),
        confirm_database=DATABASE,
    )
    with pytest.raises(QuarantineRefused, match="recent_file_protected"):
        await command.execute(**args)
    assert not (tmp_path / ".quarantine").exists()
    original = Quarantine.prepare

    def older_fixture(self, key, digest, operation, now):
        assert abs((now - datetime.now(UTC)).total_seconds()) < 10
        return original(self, key, digest, operation, now + timedelta(days=2))

    # Só no teste: operador não dispõe de flag para forçar idade de arquivos.
    monkeypatch.setattr(Quarantine, "prepare", older_fixture)
    assert (await command.execute(**args))["state"] == "quarantined"
    assert not (tmp_path / KEY).exists()


@pytest.mark.parametrize("failure", [False, True])
def test_cli_reports_result_or_sanitized_failure(monkeypatch, capsys, failure):
    from app import audio_quarantine as command

    async def execute(**kwargs):
        assert kwargs["operation"] == OP
        if failure:
            raise RuntimeError("password=never-print-this")
        return {"operation": OP, "state": "quarantined", "deleted": False}

    monkeypatch.setattr(command, "execute", execute)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audio_quarantine",
            "quarantine",
            "--operation",
            OP,
            "--key",
            KEY,
            "--sha256",
            SHA,
            "--confirm-storage",
            "/synthetic/audio",
            "--confirm-database",
            DATABASE,
        ],
    )
    if failure:
        with pytest.raises(SystemExit) as result:
            command.main()
        assert result.value.code == 2
    else:
        command.main()
    output = capsys.readouterr().out
    assert "never-print-this" not in output
    assert ("operation_unavailable" if failure else "quarantined") in output


@pytest.mark.parametrize("case", ["prod", "root", "database", "action", "missing_arguments"])
async def test_command_refuses_wrong_targets(client, tmp_path, monkeypatch, case):
    from app import audio_quarantine as command
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "speaking_storage_dir", str(tmp_path))
    # O ambiente simulado termina antes da limpeza protegida da base de testes.
    with monkeypatch.context() as patch:
        if case == "prod":
            patch.setattr(settings, "app_env", "prod")
        with pytest.raises(QuarantineRefused):
            await command.execute(
                action="invalid" if case == "action" else "quarantine",
                operation=OP,
                confirm_storage="/" if case == "root" else str(tmp_path),
                confirm_database="wrong" if case == "database" else DATABASE,
            )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("arguments", [[], ["delete"], ["quarantine"], ["restore", "--delete"]])
def test_cli_no_purge_or_implicit_target(monkeypatch, arguments):
    from app.audio_quarantine import main

    monkeypatch.setattr(sys, "argv", ["audio_quarantine", *arguments])
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 2
