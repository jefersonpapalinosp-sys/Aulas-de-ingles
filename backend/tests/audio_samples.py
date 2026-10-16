"""Silêncio sintético codificado de verdade; nenhuma voz/material de terceiros."""

import io
import wave
from fractions import Fraction
from functools import lru_cache

import av


@lru_cache
def wav(milliseconds=1000, rate=16000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes(bytes(rate * milliseconds // 1000 * 2))
    return buffer.getvalue()


@lru_cache
def encoded(kind="webm", milliseconds=1000):
    codec = {"webm": "libopus", "ogg": "libopus", "mp4": "aac", "mp3": "libmp3lame"}[kind]
    buffer = io.BytesIO()
    with av.open(buffer, mode="w", format=kind) as output:
        stream = output.add_stream(codec, rate=48000)
        stream.layout = "mono"
        audio_format = stream.codec_context.codec.audio_formats[0].name
        total = 48 * milliseconds
        for offset in range(0, total, 960):
            frame = av.AudioFrame(
                format=audio_format, layout="mono", samples=min(960, total - offset)
            )
            frame.sample_rate = 48000
            frame.pts = offset
            frame.time_base = Fraction(1, 48000)
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)
    return buffer.getvalue()
