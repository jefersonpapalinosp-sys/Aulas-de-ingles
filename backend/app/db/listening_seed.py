"""Seed editorial separado do currículo VOA; nunca remove recursos ou progresso."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ListeningResource
from app.db.seed import find_seed_file
from app.schemas.listening import ListeningResourceOut


async def seed_listening(session: AsyncSession) -> int:
    raw = json.loads(find_seed_file().with_name("listening-a2.json").read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not 1 <= len(raw) <= 200:
        raise ValueError("Catálogo de listening inválido.")
    resources = [ListeningResourceOut.model_validate(row) for row in raw]
    for field in ("slug", "source_url", "position"):
        if len({getattr(row, field) for row in resources}) != len(resources):
            raise ValueError(f"Catálogo com {field} repetido.")
    # Um lock editorial serializa cargas sem impedir leituras do aluno.
    from sqlalchemy import func

    await session.execute(select(func.pg_advisory_xact_lock(4059, 0)))
    existing = {row.slug: row for row in (await session.scalars(select(ListeningResource))).all()}
    for resource in resources:
        values = resource.model_dump()
        current = existing.get(resource.slug)
        if current is None:
            session.add(ListeningResource(**values))
        elif any(getattr(current, name) != value for name, value in values.items()):
            if resource.version <= current.version:
                raise ValueError("Alterações editoriais exigem uma versão maior.")
            for name, value in values.items():
                setattr(current, name, value)
    await session.flush()
    return len(resources)
