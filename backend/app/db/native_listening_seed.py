"""Carga imutável do piloto próprio; mídia conferida antes de gravar o catálogo."""

import hashlib
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NativeListeningVersion
from app.db.seed import find_seed_file
from app.schemas.native_listening import NativeContent


def media_root() -> Path:
    return find_seed_file().parent / "listening-native" / "audio"


def media_path(content: NativeContent) -> Path:
    path = media_root() / content.audio_file
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != content.audio_sha256:
        raise ValueError("Áudio ausente ou diferente do pacote editorial.")
    return path


async def seed_native_listening(session: AsyncSession) -> int:
    raw = json.loads(
        (find_seed_file().parent / "listening-native" / "activities.json").read_text("utf-8")
    )
    if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
        raise ValueError("Pacote nativo inválido.")
    contents = [NativeContent.model_validate(item) for item in raw]
    if len({(item.slug, item.version) for item in contents}) != len(contents):
        raise ValueError("Versão duplicada.")
    for content in contents:
        media_path(content)
    await session.execute(select(func.pg_advisory_xact_lock(4060, 0)))
    for content in contents:
        values = content.model_dump(mode="json")
        digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        existing = await session.scalar(
            select(NativeListeningVersion).where(
                NativeListeningVersion.slug == content.slug,
                NativeListeningVersion.version == content.version,
            )
        )
        if existing is not None:
            if existing.content_sha256 != digest or existing.content != values:
                raise ValueError("Conteúdo já carregado: publique uma nova versão.")
        else:
            session.add(
                NativeListeningVersion(
                    slug=content.slug,
                    version=content.version,
                    content=values,
                    content_sha256=digest,
                )
            )
    await session.flush()
    return len(contents)
