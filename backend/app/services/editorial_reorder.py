"""Opt-in, owner-only and audited application of a validated position permutation."""

from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import EditorialReorderEvent
from app.db.seed_plan import BY_NAME, SPECS, Graph, compare_graphs, read_graph
from app.services.editorial_reorder_plan import (
    catalog_sha256,
    collect_personal_reference_impact,
    compare_reorder_graphs,
)
from app.services.publication import PUBLICATION_LOCK

REASONS = ("pedagogical_sequence", "accessibility_sequence", "curriculum_reorganization")


def _receipt(event: EditorialReorderEvent, *, replayed: bool) -> dict[str, Any]:
    return {
        "operation": "reorder_editorial_content",
        "operation_key": event.operation_key,
        "operator_label": event.operator_label,
        "reason_code": event.reason_code,
        "db_actor": event.db_actor,
        "db_login": event.db_login,
        "plan_sha256": event.plan_sha256,
        "catalog_before_sha256": event.catalog_before_sha256,
        "catalog_after_sha256": event.catalog_after_sha256,
        "changed_entities": len(event.changes),
        # JSON round-trip makes the first in-memory receipt identical to a
        # replay loaded from JSONB (tuples become arrays in both cases).
        "impact_at_apply": json.loads(json.dumps(event.impact, default=str)),
        "created_at": event.created_at.isoformat(),
        "replayed": replayed,
    }


def _validate_request(
    *,
    expected_plan_sha256: str,
    operation_key: str,
    operator_label: str,
    reason_code: str,
) -> None:
    try:
        key = UUID(operation_key)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("operation_key exige UUIDv4 canônico.") from None
    if key.version != 4 or str(key) != operation_key:
        raise ValueError("operation_key exige UUIDv4 canônico.")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256):
        raise ValueError("Informe plan_sha256 canônico da prévia.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", operator_label):
        raise ValueError("Operador deve ser um identificador de 1–64 caracteres, sem texto livre.")
    if reason_code not in REASONS:
        raise ValueError("Motivo de reordenação inválido.")


async def _move_positions(
    session: AsyncSession,
    report: dict[str, Any],
    ids: dict[str, dict[tuple[Any, ...], int]],
) -> None:
    changes_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for change in report["reordered_entities"]:
        changes_by_table[change["table"]].append(change)
    for table_name, changes in sorted(changes_by_table.items()):
        table = BY_NAME[table_name].table
        maximum = int(await session.scalar(select(func.max(table.c.position))) or 0)
        if maximum + len(changes) > 2_147_483_647:
            raise ValueError("Posições temporárias excedem o limite seguro da coluna.")
        # The catalog lock freezes every sibling collection. Globally unique,
        # positive temporary positions avoid immediate UNIQUE collisions in swaps.
        for offset, change in enumerate(changes, start=1):
            row_id = ids[table_name][(change["editorial_key"],)]
            await session.execute(
                update(table).where(table.c.id == row_id).values(position=maximum + offset)
            )
        for change in changes:
            row_id = ids[table_name][(change["editorial_key"],)]
            await session.execute(
                update(table).where(table.c.id == row_id).values(position=change["after_position"])
            )


async def _write_versions(
    session: AsyncSession,
    wanted: Graph,
    report: dict[str, Any],
    ids: dict[str, dict[tuple[Any, ...], int]],
) -> None:
    lesson_table = BY_NAME["lesson_version"].table
    for transition in report["lesson_version_transitions"]:
        lesson = tuple(transition["lesson"])
        key = (lesson, transition["to_version"])
        source = dict(wanted["lesson_version"][key])
        source["lesson_id"] = ids["lesson"][lesson]
        await session.execute(insert(lesson_table).values(**source))

    review_table = BY_NAME["course_review"].table
    for transition in report["checkpoint_version_transitions"]:
        review = tuple(transition["review"])
        await session.execute(
            update(review_table)
            .where(review_table.c.id == ids["course_review"][review])
            .values(content_version=transition["to_version"])
        )


async def apply_editorial_reorder(
    session: AsyncSession,
    wanted: Graph,
    *,
    expected_plan_sha256: str,
    operation_key: str,
    operator_label: str,
    reason_code: str,
    confirm_database: str,
) -> dict[str, Any]:
    settings = get_settings()
    if (
        not settings.editorial_reorder_enabled
        or settings.app_env == "prod"
        or settings.deployment_profile == "public"
    ):
        raise ValueError("Reordenação desativada ou ambiente não liberado para ensaio local.")
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ValueError("Reordenação exige sessão nova sem alterações pendentes.")
    _validate_request(
        expected_plan_sha256=expected_plan_sha256,
        operation_key=operation_key,
        operator_label=operator_label,
        reason_code=reason_code,
    )

    async with asyncio.timeout(30), session.begin():
        if await session.scalar(text("SHOW transaction_isolation")) != "read committed":
            raise ValueError("Reordenação exige isolamento READ COMMITTED.")
        await session.execute(text("SET LOCAL statement_timeout = '20s'"))
        if await session.scalar(text("SELECT current_database()")) != confirm_database:
            raise ValueError("Banco não confirmado; nenhuma alteração realizada.")
        if not await session.scalar(text("SELECT to_regclass('editorial_reorder_event')")):
            raise ValueError("Migration b71d4f9e20c3 obrigatória para reordenação.")
        owner = await session.scalar(
            text(
                "SELECT pg_has_role(current_user, relowner, 'USAGE') "
                "FROM pg_class WHERE oid=to_regclass('editorial_reorder_event')"
            )
        )
        if not owner:
            raise ValueError("Operação exclusiva do papel proprietário/migrador, nunca runtime.")
        if not await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:namespace, :key)"),
            {"namespace": PUBLICATION_LOCK[0], "key": PUBLICATION_LOCK[1]},
        ):
            raise ValueError("Catálogo ocupado por estudo/importação; repita a prévia mais tarde.")

        existing = await session.get(EditorialReorderEvent, operation_key)
        if existing is not None:
            if (
                existing.plan_sha256,
                existing.catalog_candidate_sha256,
                existing.operator_label,
                existing.reason_code,
            ) != (
                expected_plan_sha256,
                catalog_sha256(wanted),
                operator_label,
                reason_code,
            ):
                raise ValueError("operation_key já utilizada para outra solicitação.")
            return _receipt(existing, replayed=True)

        names = ", ".join(f'"{spec.name}"' for spec in sorted(SPECS, key=lambda item: item.name))
        await session.execute(text(f"LOCK TABLE {names} IN SHARE ROW EXCLUSIVE MODE NOWAIT"))
        stored, ids = await read_graph(session)
        report = compare_reorder_graphs(wanted, stored)
        if report["plan_sha256"] != expected_plan_sha256:
            raise ValueError("Catálogo ou pacote mudou desde a prévia; obtenha um novo plano.")
        if not report["allowed"]:
            codes = sorted({blocker["code"] for blocker in report["blockers"]})
            raise ValueError("Reordenação bloqueada: " + ", ".join(codes))
        impact = await collect_personal_reference_impact(session, report, ids)

        await _move_positions(session, report, ids)
        await _write_versions(session, wanted, report, ids)
        applied, _ = await read_graph(session)
        if catalog_sha256(applied) != report["catalog_after_sha256"]:
            raise RuntimeError("Estado aplicado divergiu do plano; transação revertida.")
        final_diff = compare_graphs(wanted, applied)
        if not final_diff["allowed"] or any(
            final_diff["counts"][name] for name in ("create", "change", "omitted")
        ):
            raise RuntimeError("Verificação final do catálogo falhou; transação revertida.")

        event = EditorialReorderEvent(
            operation_key=operation_key,
            operator_label=operator_label,
            reason_code=reason_code,
            plan_sha256=expected_plan_sha256,
            catalog_before_sha256=report["catalog_before_sha256"],
            catalog_candidate_sha256=report["catalog_candidate_sha256"],
            catalog_after_sha256=report["catalog_after_sha256"],
            changes=report["reordered_entities"],
            impact={
                "personal_direct_references_preserved": impact,
                "lesson_version_transitions": report["lesson_version_transitions"],
                "checkpoint_version_transitions": report["checkpoint_version_transitions"],
            },
        )
        session.add(event)
        await session.flush()
        return _receipt(event, replayed=False)
