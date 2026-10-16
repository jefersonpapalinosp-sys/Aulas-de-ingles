"""Opt-in local rehearsal of unit archive, never deletion or automatic publication."""

import asyncio
import re
from typing import Any
from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import CourseUnit, EditorialArchiveEvent
from app.db.seed_plan import SPECS
from app.services.editorial_plan import collect_unit_archive
from app.services.publication import PUBLICATION_LOCK

REASONS = ("editorial_review", "source_unavailable", "curriculum_reorganization")


def _receipt(event: EditorialArchiveEvent, *, replayed: bool) -> dict[str, Any]:
    return {
        "operation": "archive_unit",
        "operation_key": event.operation_key,
        "course_slug": event.course_slug,
        "unit_slug": event.unit_slug,
        "before_status": event.before_status,
        "after_status": event.after_status,
        "operator_label": event.operator_label,
        "reason_code": event.reason_code,
        "db_actor": event.db_actor,
        "db_login": event.db_login,
        "catalog_sha256": event.catalog_sha256,
        "impact_at_apply": event.impact,
        "created_at": event.created_at.isoformat(),
        "replayed": replayed,
    }


async def archive_unit(
    session: AsyncSession,
    *,
    course_slug: str,
    unit_slug: str,
    expected_catalog_sha256: str,
    operation_key: str,
    operator_label: str,
    reason_code: str,
    confirm_database: str,
) -> dict[str, Any]:
    settings = get_settings()
    if (
        not settings.editorial_archive_enabled
        or settings.app_env == "prod"
        or settings.deployment_profile == "public"
    ):
        raise ValueError("Arquivamento desativado ou ambiente não liberado para ensaio local.")
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ValueError("Arquivamento exige sessão nova sem alterações pendentes.")
    try:
        key = UUID(operation_key)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("operation_key exige UUIDv4 canônico.") from None
    if key.version != 4 or str(key) != operation_key:
        raise ValueError("operation_key exige UUIDv4 canônico.")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_catalog_sha256):
        raise ValueError("Informe catalog_sha256 da prévia, não report_sha256.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", operator_label):
        raise ValueError("Operador deve ser um identificador de 1–64 caracteres, sem texto livre.")
    if reason_code not in REASONS:
        raise ValueError("Motivo de arquivamento inválido.")
    async with asyncio.timeout(30), session.begin():
        if await session.scalar(text("SHOW transaction_isolation")) != "read committed":
            raise ValueError("Arquivamento exige isolamento READ COMMITTED.")
        await session.execute(text("SET LOCAL statement_timeout = '20s'"))
        if await session.scalar(text("SELECT current_database()")) != confirm_database:
            raise ValueError("Banco não confirmado; nenhuma alteração realizada.")
        if not await session.scalar(text("SELECT to_regclass('editorial_archive_event')")):
            raise ValueError("Migration d62a0ef357b9 obrigatória para arquivamento.")
        owner = await session.scalar(
            text("""SELECT pg_has_role(current_user, relowner, 'USAGE')
            FROM pg_class WHERE oid=to_regclass('editorial_archive_event')""")
        )
        if not owner:
            raise ValueError("Operação exclusiva do papel proprietário/migrador, nunca runtime.")
        if not await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:namespace, :key)"),
            {"namespace": PUBLICATION_LOCK[0], "key": PUBLICATION_LOCK[1]},
        ):
            raise ValueError("Catálogo ocupado por estudo/importação; repita a prévia mais tarde.")
        existing = await session.get(EditorialArchiveEvent, operation_key)
        if existing is not None:
            if (
                existing.course_slug,
                existing.unit_slug,
                existing.catalog_sha256,
                existing.operator_label,
                existing.reason_code,
            ) != (course_slug, unit_slug, expected_catalog_sha256, operator_label, reason_code):
                raise ValueError("operation_key já utilizada para outra solicitação.")
            return _receipt(existing, replayed=True)
        # Freeze all editorial rows, including positional cross-unit dependencies.
        # NOWAIT avoids waiting for seed/direct SQL; no personal table is locked.
        names = ", ".join(f'"{spec.name}"' for spec in sorted(SPECS, key=lambda s: s.name))
        await session.execute(text(f"LOCK TABLE {names} IN SHARE ROW EXCLUSIVE MODE NOWAIT"))
        plan = await collect_unit_archive(session, course_slug, unit_slug)
        if plan["catalog_sha256"] != expected_catalog_sha256:
            raise ValueError("Catálogo mudou desde a prévia; obtenha uma nova prévia.")
        if plan["blockers"]:
            raise ValueError("Arquivamento bloqueado: " + ", ".join(plan["blockers"]))
        unit_id = plan["target"]["unit_id"]
        await session.execute(
            update(CourseUnit).where(CourseUnit.id == unit_id).values(status="archived")
        )
        event = EditorialArchiveEvent(
            operation_key=operation_key,
            unit_id=unit_id,
            course_slug=course_slug,
            unit_slug=unit_slug,
            operator_label=operator_label,
            reason_code=reason_code,
            before_status="published",
            after_status="archived",
            catalog_sha256=expected_catalog_sha256,
            impact={
                name: plan[name]
                for name in (
                    "editorial_rows",
                    "personal_rows_preserved",
                    "active_practice_sessions",
                    "external_checkpoint_dependencies",
                    "snapshot_table_available",
                    "policy",
                )
            },
        )
        session.add(event)
        await session.flush()
        return _receipt(event, replayed=False)
