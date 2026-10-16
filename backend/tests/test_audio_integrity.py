import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.audio_integrity import execute
from app.core.config import get_settings
from app.db.models import SpeakingAttempt, TranscriptionJob
from app.services import assistance
from app.services.audio_storage import AudioStorage
from tests.audio_samples import encoded
from tests.test_assist_quota import audio_attempt
from tests.test_speaking import conta


async def setup_audio(client, session, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "speaking_storage_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "editorial_snapshots_enabled", True)
    headers = await conta(client, "integrity")
    attempt_id = await audio_attempt(client, headers)
    attempt = await session.get(SpeakingAttempt, attempt_id)
    database = await session.scalar(select(func.current_database()))
    await session.commit()
    args = {
        "attempt_id": attempt_id,
        "confirm_storage": str(tmp_path),
        "confirm_database": database,
        "expected_key": attempt.storage_key,
    }
    return headers, attempt, args


async def test_upload_checksum_and_changed_bytes_block_download(
    client, session, monkeypatch, tmp_path
):
    headers, attempt, args = await setup_audio(client, session, monkeypatch, tmp_path)
    assert attempt.audio_sha256 == hashlib.sha256(encoded()).hexdigest()
    assert attempt.integrity_state == "verified"
    file = tmp_path / attempt.storage_key
    file.write_bytes(b"x" * file.stat().st_size)
    response = await client.get(f"/api/speaking/attempts/{attempt.id}/audio", headers=headers)
    assert response.status_code == 409 and encoded() not in response.content
    assert (await execute(**args))["state"] == "changed"
    await execute(**args, apply=True)
    listed = (await client.get("/api/speaking/attempts", headers=headers)).json()
    assert listed[0]["integrity_state"] == "changed"


async def test_restore_missing_audio_without_journal_keeps_identity(
    client, session, monkeypatch, tmp_path
):
    headers, attempt, args = await setup_audio(client, session, monkeypatch, tmp_path)
    file = tmp_path / attempt.storage_key
    original = file.read_bytes()
    backup = tmp_path / "backup.webm"
    backup.write_bytes(original)
    digest = hashlib.sha256(original).hexdigest()
    file.unlink()  # Apenas perda sintética neste teste isolado.
    assert (await execute(**args, apply=True))["state"] == "missing"
    result = await execute(**args, apply=True, restore_file=str(backup), sha256=digest)
    assert result["restored"] and result["state"] == "verified"
    assert (
        await client.get(f"/api/speaking/attempts/{attempt.id}/audio", headers=headers)
    ).content == original
    assert backup.read_bytes() == original
    await session.refresh(attempt)
    assert attempt.storage_key != args["expected_key"] and attempt.id == args["attempt_id"]
    with pytest.raises(ValueError, match="reference_changed"):
        await execute(**args, apply=True)


async def test_legacy_baseline_is_explicit_not_invented(client, session, monkeypatch, tmp_path):
    _, attempt, args = await setup_audio(client, session, monkeypatch, tmp_path)
    attempt.audio_sha256, attempt.integrity_state = None, "unknown"
    await session.commit()
    assert (await execute(**args))["state"] == "unknown"
    assert (await execute(**args, apply=True))["state"] == "unknown"
    await session.refresh(attempt)
    assert attempt.audio_sha256 is None
    await session.commit()
    assert (await execute(**args, apply=True, baseline=True))["baseline_established"]
    await session.refresh(attempt)
    assert attempt.audio_sha256 == hashlib.sha256(encoded()).hexdigest()


async def test_restore_refuses_existing_file_bad_checksum_and_unconfirmed_target(
    client, session, monkeypatch, tmp_path
):
    _, attempt, args = await setup_audio(client, session, monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="target_confirmation"):
        await execute(attempt_id=attempt.id, apply=True)
    with pytest.raises(ValueError, match="apply_required"):
        await execute(attempt_id=attempt.id, baseline=True)
    with pytest.raises(ValueError, match="database_confirmation"):
        await execute(**{**args, "confirm_database": "other"}, apply=True)
    with pytest.raises(ValueError, match="backup_does_not_match"):
        await execute(**args, apply=True, restore_file=str(tmp_path / "copy.webm"), sha256="0" * 64)
    with pytest.raises(ValueError, match="existing_file_protected"):
        await execute(
            **args,
            apply=True,
            restore_file=str(tmp_path / "copy.webm"),
            sha256=attempt.audio_sha256,
        )


def test_verified_reader_rejects_symlink_oversize_and_hash_mismatch(tmp_path):
    storage = AudioStorage(str(tmp_path))
    key = storage.save(b"synthetic audio", "audio/wav")
    with pytest.raises(ValueError):
        storage.read_verified(key, None, 3)
    with pytest.raises(ValueError):
        storage.read_verified(key, "0" * 64, 100)
    (tmp_path / "link.wav").symlink_to(tmp_path / key)
    with pytest.raises(OSError):
        storage.read_verified("link.wav", None, 100)
    assert not storage.matches("link.wav", b"synthetic audio")
    with pytest.raises(ValueError):
        storage.read_verified("..", None, 100)


async def test_expired_transcription_hidden_in_history_export_and_rating(
    client, session, monkeypatch, tmp_path
):
    headers, attempt, _ = await setup_audio(client, session, monkeypatch, tmp_path)
    settings = get_settings()
    monkeypatch.setattr(settings, "assisted_features_enabled", True)
    monkeypatch.setattr(settings, "assist_transcription_url", "http://provider.test/stt")
    monkeypatch.setattr(
        assistance,
        "call_transcription_provider",
        lambda *a, **k: pytest.fail("No provider permitted"),
    )
    response = await client.post(
        f"/api/speaking/attempts/{attempt.id}/transcription", headers=headers
    )
    job = await session.get(TranscriptionJob, response.json()["id"])
    job.transcript_text = "private expired text"
    job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()
    assert (await client.get("/api/speaking/attempts", headers=headers)).json()[0][
        "transcription"
    ] is None
    exported = await client.get("/api/me/export", headers=headers)
    assert exported.status_code == 200 and "private expired text" not in exported.text
    assert (
        await client.put(
            f"/api/speaking/transcriptions/{job.id}/rating",
            headers=headers,
            json={"rating": "helpful"},
        )
    ).status_code == 404
