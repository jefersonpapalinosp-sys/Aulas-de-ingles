"""Isolamento exclusivo do pytest; nunca importar na aplicação ou no worker."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine, get_session
from app.db.test_safety import IDENTITY_SQL, validate_test_identity, validate_test_target
from app.main import create_app

SEED_TABLES = frozenset({
    "content_source",
    "course",
    "course_review",
    "course_review_question",
    "course_unit",
    "exercise",
    "exercise_answer",
    "exercise_hint",
    "grammar_block",
    "grammar_row",
    "lesson",
    "lesson_goal",
    "lesson_media",
    "lesson_version",
    "phrase",
    "pronunciation_note",
    "transcript_cue",
    "vocab_item",
    "writing_prompt",
})

TRANSIENT_TABLES = frozenset({
    "account_deletion_file",
    "account_deletion_job",
    "app_user",
    "assist_reservation",
    "auth_rate_bucket",
    "course_review_attempt",
    "dialogue_turn",
    "editorial_archive_event",
    "editorial_reorder_event",
    "evidence_content_snapshot",
    "exercise_attempt",
    "lesson_progress",
    "media_progress",
    "notebook_entry",
    "practice_session",
    "practice_session_item",
    "refresh_session",
    "review_card",
    "review_event",
    "review_item",
    "skill_evidence",
    "speaking_attempt",
    "speaking_dialogue",
    "step_progress",
    "study_active_interval",
    "study_activity_event",
    "study_activity_session",
    "study_plan",
    "study_session_progress",
    "transcription_job",
    "worker_heartbeat",
    "writing_draft",
    "writing_feedback",
    "writing_revision",
})


def assert_table_inventory() -> None:
    overlap = SEED_TABLES & TRANSIENT_TABLES
    if overlap or set(Base.metadata.tables) != SEED_TABLES | TRANSIENT_TABLES:
        raise RuntimeError("DB-49: classifique as tabelas de teste antes de limpar o banco.")


async def reset_transient_data(session: AsyncSession) -> None:
    """Limpa apenas tabelas classificadas, após identidade real, sem CASCADE.

    A transação/commit pertencem ao chamador. RESTRICT impede que uma FK nova
    leve junto conteúdo de seed. Identificadores são constantes, não entrada.
    """
    settings = get_settings()
    validate_test_target(settings.database_url, settings.app_env)
    assert_table_inventory()
    identity = (await session.execute(text(IDENTITY_SQL))).one_or_none()
    validate_test_identity(identity)
    tables = ", ".join(f'"public"."{name}"' for name in sorted(TRANSIENT_TABLES))
    await session.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY RESTRICT"))


@asynccontextmanager
async def catalog_transaction() -> AsyncIterator[tuple[AsyncSession, AsyncClient]]:
    """Commits do cenário/API liberam savepoints; a transação externa sempre volta.

    Uso opt-in para conteúdo editorial. Concorrência, locks e workers continuam
    usando conexões/transações independentes na fixture padrão.
    """
    async with get_engine().connect() as connection:
        transaction = await connection.begin()
        factory = async_sessionmaker(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        app = create_app()

        async def dependency() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        app.dependency_overrides[get_session] = dependency
        try:
            async with factory() as session, AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield session, client
        finally:
            app.dependency_overrides.clear()
            await transaction.rollback()
