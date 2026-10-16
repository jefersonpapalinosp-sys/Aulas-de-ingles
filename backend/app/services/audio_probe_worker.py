"""Processo descartável: recebe bytes por stdin, nunca URL/caminho do aluno.

Executado com Python -I, ambiente mínimo e limites POSIX antes de importar PyAV.
Não é um sandbox de segurança do sistema operacional.
"""

import io
import json
import math
import resource
import struct
import sys
from fractions import Fraction
from typing import Any

MAX_BYTES = 2_000_000
MAX_SECONDS = 30
FORMATS = "matroska,webm,ogg,mov,mp3,wav"
CODECS = {
    "audio/webm": {"opus", "vorbis"},
    "audio/ogg": {"opus", "vorbis"},
    "audio/mp4": {"aac", "alac", "opus"},
    "audio/mpeg": {"mp3", "mp3float"},
    "audio/wav": {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_u8", "pcm_f32le"},
}
CONTAINERS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mov",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
}


class InvalidAudio(Exception):
    pass


def deny_external(*args: Any) -> None:
    raise InvalidAudio("invalid")


def inspect(data: bytes, mime: str) -> dict[str, str | int]:
    import av

    if not data or len(data) > MAX_BYTES:
        raise InvalidAudio("invalid")
    # RIFF informa seu comprimento: não aceitar WAV truncado que um decoder toleraria.
    if mime == "audio/wav" and (
        len(data) < 12
        or data[:4] != b"RIFF"
        or data[8:12] != b"WAVE"
        or struct.unpack_from("<I", data, 4)[0] + 8 != len(data)
    ):
        raise InvalidAudio("invalid")
    # Nenhum protocolo file/http/tcp/data/concat. BytesIO permite seek para MP4.
    with av.open(
        io.BytesIO(data),
        mode="r",
        io_open=deny_external,
        options={
            "format_whitelist": FORMATS,
            "protocol_whitelist": "pipe",
            "probesize": str(MAX_BYTES),
            "analyzeduration": "3000000",
            "max_streams": "2",
        },
    ) as container:
        streams = list(container.streams)
        if len(streams) != 1 or streams[0].type != "audio":
            raise InvalidAudio("unsupported")
        stream = streams[0]
        assert isinstance(stream, av.audio.stream.AudioStream)
        context = stream.codec_context
        if CONTAINERS.get(mime) not in container.format.name.split(
            ","
        ) or context.name not in CODECS.get(mime, set()):
            raise InvalidAudio("unsupported")
        if not 8000 <= context.sample_rate <= 48000 or not 1 <= context.channels <= 2:
            raise InvalidAudio("unsupported")
        context.thread_count = 1
        context.options = {"err_detect": "explode"}
        decoded = Fraction(0)
        first = None
        last = None
        span = Fraction(0)
        for frames, frame in enumerate(container.decode(stream), 1):
            if not isinstance(frame, av.AudioFrame):
                raise InvalidAudio("unsupported")
            if (
                frames > 10000
                or not 8000 <= frame.sample_rate <= 48000
                or not 1 <= len(frame.layout.channels) <= 2
                or frame.is_corrupt
            ):
                raise InvalidAudio("invalid")
            duration = Fraction(frame.samples, frame.sample_rate)
            decoded += duration
            if frame.pts is not None and frame.time_base is not None:
                start = frame.pts * frame.time_base
                if last is not None and start < last:
                    raise InvalidAudio("invalid")
                first = start if first is None else first
                last = start
                span = max(span, start + duration - first)
            if max(decoded, span) > MAX_SECONDS:
                raise InvalidAudio("too_long")
        if decoded <= 0:
            raise InvalidAudio("invalid")
        return {
            "duration_ms": math.ceil(max(decoded, span) * 1000),
            "codec": context.name,
            "container": container.format.name,
        }


def main() -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        if sys.platform == "linux":
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
        data = sys.stdin.buffer.read(MAX_BYTES + 1)
        result = inspect(data, sys.argv[1])
    except InvalidAudio as error:
        result = {"error": str(error)}
    except (ImportError, MemoryError):
        result = {"error": "unavailable"}
    except Exception:
        # Não devolver stderr, tags, texto do arquivo ou caminhos ao cliente/log.
        result = {"error": "invalid"}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
