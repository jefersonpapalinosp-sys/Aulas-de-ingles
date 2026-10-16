"""Read-only unit archive impact. Never an authorization to mutate the catalog.

Aggregates only: no student IDs, answers, drafts, filenames or credentials in the
report. A fresh repeatable-read transaction prevents mixing different instants.
"""

import asyncio
import hashlib
import json
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import get_settings
from app.db import editorial_identity
from app.db.models import Course
from app.db.seed_plan import SPECS, _hash, _json, read_graph
from app.services.editorial_history import schema_available

# Explicit topological allowlist. These links scope actual rows, not an estimate
# based on how many users studied the lesson. Nullable/orphan origins are disclosed.
PERSONAL_LINKS = {
    "lesson_progress": ("lesson_id", "lesson"),
    "study_session_progress": ("lesson_id", "lesson"),
    "step_progress": ("study_session_id", "study_session_progress"),
    "practice_session": ("lesson_id", "lesson"),
    "practice_session_item": ("practice_session_id", "practice_session"),
    "exercise_attempt": ("exercise_id", "exercise"),
    "writing_draft": ("prompt_id", "writing_prompt"),
    "writing_revision": ("draft_id", "writing_draft"),
    "writing_feedback": ("prompt_id", "writing_prompt"),
    "speaking_attempt": ("transcript_cue_id", "transcript_cue"),
    "transcription_job": ("speaking_attempt_id", "speaking_attempt"),
    "review_item": ("lesson_id", "lesson"),
    "review_event": ("item_id", "review_item"),
    "review_card": ("vocab_item_id", "vocab_item"),
    "media_progress": ("media_id", "lesson_media"),
    "notebook_entry": ("lesson_id", "lesson"),
    "study_activity_session": ("lesson_id", "lesson"),
    "study_activity_event": ("session_id", "study_activity_session"),
    "study_active_interval": ("lesson_id", "lesson"),
    "course_review_attempt": ("review_id", "course_review"),
}
SNAPSHOT_LINKS = {
    "exercise_attempt_id": "exercise_attempt",
    "practice_item_id": "practice_session_item",
    "writing_feedback_id": "writing_feedback",
    "speaking_attempt_id": "speaking_attempt",
    "checkpoint_attempt_id": "course_review_attempt",
}
SKILL_SOURCES = ("exercise_attempt", "writing_feedback", "speaking_attempt")
PREVIEW_TIMEOUT_SECONDS = 30


async def preview_unit_archive(
    session: AsyncSession, course_slug: str, unit_slug: str
) -> dict[str, Any]:
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise ValueError("A prévia exige sessão nova, sem transação ou alterações pendentes.")
    async with asyncio.timeout(PREVIEW_TIMEOUT_SECONDS), session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        await session.execute(text("SET LOCAL statement_timeout = '20s'"))
        return await collect_unit_archive(session, course_slug, unit_slug)


async def collect_unit_archive(
    session: AsyncSession, course_slug: str, unit_slug: str
) -> dict[str, Any]:
    """Caller owns transaction: read-only preview, or locked archive application."""
    tables = Course.metadata.tables
    course, unit = tables["course"], tables["course_unit"]
    target = (
        (
            await session.execute(
                select(
                    course.c.id.label("course_id"),
                    course.c.status.label("course_status"),
                    unit.c.id.label("unit_id"),
                    unit.c.status.label("unit_status"),
                )
                .select_from(unit.join(course, unit.c.course_id == course.c.id))
                .where(course.c.slug == course_slug, unit.c.slug == unit_slug)
            )
        )
        .mappings()
        .one_or_none()
    )
    if target is None:
        raise ValueError("Curso/unidade não encontrado; nenhuma alteração realizada.")
    scopes: dict[str, ColumnElement[bool]] = {
        "course": course.c.id == target["course_id"],
        "course_unit": unit.c.id == target["unit_id"],
    }

    def ids(name: str) -> Any:
        return select(tables[name].c.id).where(scopes[name]).correlate(None)

    editorial_rows: dict[str, int] = {}
    for spec in SPECS:
        if spec.name not in scopes:
            scopes[spec.name] = and_(
                *(spec.table.c[field].in_(ids(parent)) for field, parent in spec.refs)
            )
        editorial_rows[spec.name] = int(
            await session.scalar(
                select(func.count()).select_from(spec.table).where(scopes[spec.name])
            )
            or 0
        )
    for name, (field, parent) in PERSONAL_LINKS.items():
        scopes[name] = tables[name].c[field].in_(ids(parent))
    skill = tables["skill_evidence"]
    scopes["skill_evidence"] = or_(
        *(
            and_(skill.c.source_type == name, skill.c.source_id.in_(ids(name)))
            for name in SKILL_SOURCES
        )
    )
    snapshots_present = await schema_available(session)
    if snapshots_present:
        snapshot = tables["evidence_content_snapshot"]
        scopes["evidence_content_snapshot"] = or_(
            *(snapshot.c[field].in_(ids(parent)) for field, parent in SNAPSHOT_LINKS.items())
        )
    personal_names = [*PERSONAL_LINKS, "skill_evidence"]
    if snapshots_present:
        personal_names.append("evidence_content_snapshot")
    personal_rows = {
        name: int(
            await session.scalar(select(func.count()).select_from(tables[name]).where(scopes[name]))
            or 0
        )
        for name in personal_names
    }
    practice = tables["practice_session"]
    active_practices = int(
        await session.scalar(
            select(func.count())
            .select_from(practice)
            .where(scopes["practice_session"], practice.c.status == "active")
        )
        or 0
    )
    # Checkpoints in OTHER units can cite a lesson in this unit (e.g. 40–44
    # listens to lesson 40 in 31–40). These references have no database FK.
    review, question, lesson = (
        tables["course_review"],
        tables["course_review_question"],
        tables["lesson"],
    )
    lesson_numbers = select(lesson.c.number).where(scopes["lesson"]).correlate(None)
    question_references = (
        select(question.c.id)
        .join(lesson, question.c.lesson_numbers.op("@>")(func.jsonb_build_array(lesson.c.number)))
        .where(question.c.review_id == review.c.id, scopes["lesson"])
        .correlate(review)
        .exists()
    )
    external_checkpoints = int(
        await session.scalar(
            select(func.count())
            .select_from(review.join(unit, review.c.unit_id == unit.c.id))
            .where(
                unit.c.course_id == target["course_id"],
                unit.c.id != target["unit_id"],
                or_(
                    review.c.review_lesson_number.in_(lesson_numbers),
                    review.c.listening_lesson_number.in_(lesson_numbers),
                    question_references,
                ),
            )
        )
        or 0
    )
    graph, identifiers = await read_graph(session)
    database = await session.scalar(text("SELECT current_database()"))
    catalog_sha256 = _hash(
        {
            "database": database,
            "target": dict(target),
            "rows": {name: sorted(rows.values(), key=_json) for name, rows in graph.items()},
            "ids": {
                name: sorted((_json(key), value) for key, value in rows.items())
                for name, rows in identifiers.items()
            },
        }
    )
    stable_keys = await editorial_identity.schema_available(session)
    audit_present = bool(
        await session.scalar(text("SELECT to_regclass('editorial_archive_event')"))
    )
    settings = get_settings()
    blockers = []
    if not stable_keys or not snapshots_present or not audit_present:
        blockers.append("editorial_migrations_required")
    if not settings.editorial_archive_enabled:
        blockers.append("local_archive_disabled")
    if settings.app_env == "prod" or settings.deployment_profile == "public":
        blockers.append("production_rollout_not_released")
    if target["course_status"] != "published" or target["unit_status"] != "published":
        blockers.append("target_not_published")
    if external_checkpoints:
        blockers.append("external_checkpoint_dependencies")
    report = {
        "schema_version": "1.1",
        "operation": "archive_unit_preview",
        "dry_run": True,
        "apply_available": not blockers,
        "database": database,
        "catalog_sha256": catalog_sha256,
        "identity_storage": "persisted" if stable_keys else "legacy_projection",
        "archive_audit_available": audit_present,
        "target": {"course_slug": course_slug, "unit_slug": unit_slug, **dict(target)},
        "editorial_rows": editorial_rows,
        "personal_rows_preserved": personal_rows,
        "active_practice_sessions": active_practices,
        "external_checkpoint_dependencies": external_checkpoints,
        "limits": {"total_seconds": PREVIEW_TIMEOUT_SECONDS, "statement_seconds": 20},
        "snapshot_table_available": snapshots_present,
        "unattributed": [
            "Recibos de revisão sem item e evidências sem origem resolvível não são "
            "atribuídos a esta unidade; não significa que não existam.",
            "Sessões de acesso, cotas de assistência, plano semanal, backups, caches "
            "e rascunhos locais não são atribuídos por unidade.",
        ],
        "policy": {
            "delete_personal_rows": False,
            "delete_audio_files": False,
            "rewrite_results": False,
            "historical_read": "owner_only",
            "new_curricular_activity": "unavailable_after_archive",
            "existing_personal_review": "preserved",
        },
        "blockers": blockers,
        "rollout_limitations": [
            "historical_ui_and_public_cache_invalidation",
            "completion_rule_version_and_recovery_rehearsal",
        ],
    }
    digest = hashlib.sha256(
        json.dumps(report, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    # This hash identifies this aggregate report, NOT the content version,
    # an executable plan, a lock, or permission for a later mutation.
    return {
        **report,
        "report_sha256": digest,
        "snapshot_at": str(await session.scalar(select(func.transaction_timestamp()))),
        "notice": "Somente prévia, sem reserva. Aplicação local exige confirmação do banco, "
        "catalog_sha256 atual e operador; report_sha256 não autoriza escrita. "
        "Contagens por tabela não são usuários únicos.",
    }
