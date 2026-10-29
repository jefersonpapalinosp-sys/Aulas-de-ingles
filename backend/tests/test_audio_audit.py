import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from app.services.audio_audit import AudioReference, inventory

KEY = "a" * 32 + ".wav"
OTHER = "b" * 32 + ".webm"


@pytest.mark.timezone
def test_inventory_is_read_only_protects_references_recent_temp_and_links(tmp_path):
    now = datetime.now(UTC)
    (tmp_path / KEY).write_bytes(b"voice")
    (tmp_path / OTHER).write_bytes(b"orphan")
    (tmp_path / "upload.webm.tmp").write_bytes(b"pending")
    (tmp_path / "unknown.txt").write_text("do not remove")
    (tmp_path / "linked.wav").symlink_to(tmp_path / KEY)
    references = [
        AudioReference(1, "ready", KEY, 4, now),
        AudioReference(2, "ready", "missing.wav", 12, now),
        AudioReference(3, "pending", None, None, now),
        AudioReference(4, "ready", "../outside", 1, now),
    ]
    # Relógio avançado apenas na fixture: ctime real impede falsificar idade via utime.
    report = inventory(tmp_path, references, now + timedelta(days=2))
    assert report["dry_run"] and report["complete"]
    assert report["counts"] == {
        "pending_old": 1,
        "invalid_reference": 1,
        "referenced": 1,
        "orphan_candidate": 1,
        "temporary_protected": 1,
        "unclassified_protected": 1,
        "unsafe_entry": 1,
        "size_mismatch": 1,
        "missing_file": 1,
    }
    reference = next(item for item in report["findings"] if item["kind"] == "referenced")
    assert reference["sha256"] == hashlib.sha256(b"voice").hexdigest()
    assert (tmp_path / KEY).read_bytes() == b"voice"
    assert len(list(tmp_path.iterdir())) == 5
    recent = inventory(tmp_path, references, now)
    assert recent["counts"]["recent_protected"] == 3
    assert "orphan_candidate" not in recent["counts"]


@pytest.mark.timezone
def test_incomplete_snapshot_and_scan_budget_never_authorize_orphan_cleanup(tmp_path):
    now = datetime.now(UTC) + timedelta(days=2)
    (tmp_path / KEY).write_bytes(b"voice")
    (tmp_path / OTHER).write_bytes(b"voice")
    report = inventory(tmp_path, [], now, snapshot_complete=False)
    assert not report["complete"] and "orphan_candidate" not in report["counts"]
    report = inventory(tmp_path, [], now, max_hash_bytes=1)
    assert not report["complete"] and report["counts"]["hash_budget"] == 2
    report = inventory(tmp_path, [], now, max_files=1)
    assert not report["complete"] and report["counts"]["scan_limit"] == 1
    report = inventory(tmp_path, [], now, max_seconds=0)
    assert not report["complete"] and report["files_scanned"] == 0


@pytest.mark.timezone
def test_missing_or_symlinked_root_is_not_created_or_followed(tmp_path):
    absent = tmp_path / "absent"
    report = inventory(absent, [], datetime.now(UTC))
    assert not report["complete"] and not absent.exists()
    linked = tmp_path / "link"
    linked.symlink_to(tmp_path, target_is_directory=True)
    assert not inventory(linked, [], datetime.now(UTC))["complete"]
    with pytest.raises(ValueError):
        inventory(tmp_path, [], datetime.now(UTC), min_age=1)


@pytest.mark.timezone
def test_file_changing_during_hash_is_not_an_orphan_candidate(tmp_path, monkeypatch):
    import os

    (tmp_path / KEY).write_bytes(b"original")
    original = os.read

    def changing(fd, size):
        result = original(fd, size)
        (tmp_path / KEY).write_bytes(b"modified")
        return result

    monkeypatch.setattr(os, "read", changing)
    report = inventory(tmp_path, [], datetime.now(UTC) + timedelta(days=2))
    assert not report["complete"]
    assert report["counts"] == {"changed_protected": 1}


async def test_database_snapshot_is_read_only_and_releases_connection_before_files(
    client, tmp_path, monkeypatch
):
    from sqlalchemy import event

    from app import audio_audit as command
    from app.core.config import get_settings
    from app.db.session import get_engine
    from tests.test_speaking import conta, cue_id

    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    headers = await conta(client, "audit-only")
    created = await client.post(
        "/api/speaking/attempts",
        headers=headers,
        json={
            "cue_id": await cue_id(client),
            "duration_ms": 1000,
            "consent": True,
        },
    )
    assert created.status_code == 201
    engine = get_engine()
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    original = command.inventory

    def inspect_pool(*args, **kwargs):
        assert engine.pool.checkedout() == 0
        return original(*args, **kwargs)

    monkeypatch.setattr(command, "inventory", inspect_pool)
    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        report = await command.audit()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert report["complete"] and report["references_scanned"] == 1
    assert any("REPEATABLE READ, READ ONLY" in statement for statement in statements)
    assert not any(statement.startswith(("DELETE", "UPDATE", "INSERT")) for statement in statements)
    assert (
        await client.delete(f"/api/speaking/attempts/{created.json()['id']}", headers=headers)
    ).status_code == 204


@pytest.mark.parametrize("args", [[], ["--apply"], ["--dry-run", "--delete"]])
def test_cli_never_offers_mutation_mode(monkeypatch, args):
    import sys

    from app.audio_audit import main

    monkeypatch.setattr(sys, "argv", ["audio_audit", *args])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
