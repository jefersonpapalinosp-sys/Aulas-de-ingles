"""Decodificação real e limites do processo, sem som/voz pessoal."""

import asyncio

import pytest
from fastapi import HTTPException

from app.services import audio_inspection as service
from app.services.audio_probe_worker import InvalidAudio, inspect
from tests.audio_samples import encoded, wav


@pytest.mark.parametrize(
    "kind,mime",
    [
        ("webm", "audio/webm"),
        ("ogg", "audio/ogg"),
        ("mp4", "audio/mp4"),
        ("mp3", "audio/mpeg"),
        ("wav", "audio/wav"),
    ],
)
async def test_real_container_codec_and_decoded_duration(kind, mime):
    data = wav() if kind == "wav" else encoded(kind)
    # Chamada direta cobre o algoritmo; subprocesso confirma o empacotamento/limites.
    result = inspect(data, mime)
    assert 1000 <= result["duration_ms"] <= 1001
    assert await service.inspect_audio(data, mime) == result["duration_ms"]


@pytest.mark.parametrize(
    "data,mime,code",
    [
        (b"not audio", "audio/webm", 422),
        (b"#EXTM3U\nhttp://127.0.0.1:8010/api/health", "audio/webm", 422),
        (b"ffconcat version 1.0\nfile /etc/passwd", "audio/webm", 422),
        (wav()[:-100], "audio/wav", 422),
        (wav(), "audio/mp4", 415),
        (wav(30_001), "audio/wav", 422),
        (wav(rate=96000), "audio/wav", 415),
        (bytes(2_000_001), "audio/wav", 413),
    ],
)
async def test_bad_files_fake_mime_oversize_duration_and_external_playlists(data, mime, code):
    with pytest.raises(HTTPException) as error:
        await service.inspect_audio(data, mime)
    assert error.value.status_code == code


async def test_exact_duration_limit_and_compressed_long_audio():
    assert await service.inspect_audio(wav(30_000), "audio/wav") == 30_000
    data = encoded(milliseconds=31_000)
    assert len(data) < 2_000_000
    with pytest.raises(HTTPException) as error:
        await service.inspect_audio(data, "audio/webm")
    assert error.value.status_code == 422
    with pytest.raises(InvalidAudio, match="too_long"):
        inspect(data, "audio/webm")


async def test_busy_and_failed_spawn_release_capacity(monkeypatch):
    monkeypatch.setattr(service, "_active", service.MAX_INSPECTIONS)
    with pytest.raises(HTTPException) as error:
        await service.inspect_audio(wav(), "audio/wav")
    assert error.value.status_code == 503
    monkeypatch.setattr(service, "_active", 0)

    async def unavailable(*args, **kwargs):
        raise OSError("private details must not be exposed")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", unavailable)
    with pytest.raises(HTTPException) as error:
        await service.inspect_audio(wav(), "audio/wav")
    assert error.value.status_code == 503
    assert "private" not in error.value.detail
    assert service._active == 0


@pytest.mark.parametrize("action", ["timeout", "cancel", "output_limit", "crash"])
async def test_child_is_reaped_on_timeout_cancel_or_overflow(tmp_path, monkeypatch, action):
    script = tmp_path / "probe.py"
    script.write_text(
        "import sys,time\nsys.stdin.buffer.read()\n"
        + {
            "timeout": "time.sleep(10)",
            "cancel": "time.sleep(10)",
            "output_limit": "print('x' * 10000)",
            "crash": "sys.exit(1)",
        }[action]
    )
    monkeypatch.setattr(service, "WORKER", script)
    monkeypatch.setattr(service, "INSPECTION_TIMEOUT", 0.15)
    original = asyncio.create_subprocess_exec
    children = []

    async def spawn(*args, **kwargs):
        assert "DATABASE_URL" not in kwargs["env"]
        assert "-I" in args
        process = await original(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(service.inspect_audio(wav(), "audio/wav"))
    if action == "cancel":
        while not children:
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(HTTPException) as error:
            await task
        assert error.value.status_code == 503
    assert children and children[0].returncode is not None
    assert service._active == 0


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_worker_limits_before_loading_decoder_without_inheriting_secrets(
    monkeypatch, capsys, platform
):
    import io
    import json
    from types import SimpleNamespace

    from app.services import audio_probe_worker as worker

    limits = {}
    monkeypatch.setattr(
        worker.resource, "setrlimit", lambda kind, value: limits.update({kind: value})
    )
    monkeypatch.setattr(worker.sys, "platform", platform)
    monkeypatch.setattr(worker.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"test")))
    monkeypatch.setattr(worker.sys, "argv", ["probe", "audio/wav"])

    def decoder(data, mime):
        assert limits[worker.resource.RLIMIT_CPU] == (5, 5)
        assert limits[worker.resource.RLIMIT_NOFILE] == (32, 32)
        assert limits[worker.resource.RLIMIT_CORE] == (0, 0)
        if platform == "linux":
            assert limits[worker.resource.RLIMIT_AS] == (512 * 1024**2,) * 2
        return {"duration_ms": 1000}

    monkeypatch.setattr(worker, "inspect", decoder)
    worker.main()
    assert json.loads(capsys.readouterr().out)["duration_ms"] == 1000


def test_worker_refuses_video_and_multiple_audio_streams():
    import io
    from fractions import Fraction

    import av

    for video in (False, True):
        buffer = io.BytesIO()
        with av.open(buffer, mode="w", format="mp4") as output:
            streams = [
                output.add_stream("mpeg4" if video else "aac", rate=25 if video else 48000)
                for _ in range(1 if video else 2)
            ]
            for stream in streams:
                if video:
                    stream.width = stream.height = 16
                else:
                    stream.layout = "mono"
            for stream in streams:
                if video:
                    frame = av.VideoFrame(16, 16, "yuv420p")
                else:
                    frame = av.AudioFrame(format="fltp", layout="mono", samples=1024)
                    frame.sample_rate = 48000
                frame.pts = 0
                frame.time_base = Fraction(1, 25 if video else 48000)
                for plane in frame.planes:
                    plane.update(bytes(plane.buffer_size))
                for packet in stream.encode(frame):
                    output.mux(packet)
                for packet in stream.encode(None):
                    output.mux(packet)
        with pytest.raises(InvalidAudio, match="unsupported"):
            inspect(buffer.getvalue(), "audio/mp4")
