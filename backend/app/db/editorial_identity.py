"""Entity identity, never a content version or a reconstruction of old content.

The legacy coordinate is used ONLY to bootstrap the current baseline. Persisted
keys travel with the entity on every subsequent edit/reorder; never regenerate
them from position, wording or parent. New authored entities use explicit UUIDs.
"""

import json
from typing import Any
from uuid import RFC_4122, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TABLES = (
    "course_review_question",
    "exercise",
    "lesson_media",
    "transcript_cue",
    "vocab_item",
    "writing_prompt",
)
NAMESPACE = UUID("605c62ea-e8be-4cb1-a7ce-436f7bd706f0")


def bootstrap_key(table: str, *coordinate: Any) -> str:
    if table not in TABLES:
        raise ValueError("Tipo sem contrato de identidade editorial.")
    name = json.dumps([table, *coordinate], ensure_ascii=False, separators=(",", ":"))
    return str(uuid5(NAMESPACE, name))


def validate_key(value: Any) -> str:
    try:
        parsed = UUID(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if (
        parsed is None
        or parsed.variant != RFC_4122
        or parsed.version not in {4, 5}
        or str(parsed) != value
    ):
        raise ValueError("editorial_key exige UUID v4/v5 canônico e explícito.")
    return str(parsed)


async def schema_available(session: AsyncSession) -> bool:
    count = await session.scalar(
        text("""
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema = current_schema() AND column_name = 'editorial_key'
          AND table_name = ANY(:names)
    """),
        {"names": list(TABLES)},
    )
    return bool(count == len(TABLES))


def projected_legacy_key(name: str, values: dict[str, Any], graph: Any) -> str:
    """Read-only preview on the old schema; never claimed as a persisted key."""
    if name == "course_review_question":
        unit_key = values["review_id"][0]
        return bootstrap_key(name, unit_key[0][0], unit_key[1], values["position"])
    if name == "transcript_cue":
        media = graph["lesson_media"][values["media_id"]]
        lesson_key = media["lesson_id"]
        return bootstrap_key(
            name, lesson_key[0][0], lesson_key[1], media["position"], values["position"]
        )
    lesson_key = values["lesson_id"]
    discriminator = values["term"] if name == "vocab_item" else values["position"]
    return bootstrap_key(name, lesson_key[0][0], lesson_key[1], discriminator)
