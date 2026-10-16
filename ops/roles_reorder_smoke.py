"""Reorder receipt under migrator identity; the whole rehearsal rolls back."""

import asyncio
from copy import deepcopy
from uuid import uuid4

from app.core.config import get_settings
from app.db import seed
from app.db.models import EditorialReorderEvent
from app.db.seed_plan import seed_graph
from app.db.session import dispose_engine, get_engine, get_sessionmaker
from app.services.editorial_reorder import apply_editorial_reorder
from app.services.editorial_reorder_plan import preview_editorial_reorder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker


def candidate():
    courses = deepcopy(seed.load_course_seed())
    lessons = deepcopy(seed.load_seed())
    lesson = lessons[0]
    first, second = lesson["exercises"][:2]
    first["position"], second["position"] = second["position"], first["position"]
    lesson.update(
        content_version=2,
        editorial_status="reviewed",
        review_note="Reordenação sintética revisada no laboratório de papéis.",
        reviewed_at="2026-10-15T12:00:00-03:00",
    )
    return seed_graph(courses, lessons)


async def main():
    settings = get_settings()
    assert settings.database_purpose == "migrator" and settings.app_env == "dev"
    settings.editorial_reorder_enabled = True
    graph = candidate()
    async with get_sessionmaker()() as session:
        plan = await preview_editorial_reorder(session, graph)
    assert plan["allowed"] and not plan["apply_available"]

    engine = get_engine()
    async with engine.connect() as connection:
        before = await connection.scalar(
            select(func.count()).select_from(EditorialReorderEvent)
        )
        await connection.rollback()
        async with connection.begin():
            factory = async_sessionmaker(
                connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            request = {
                "expected_plan_sha256": plan["plan_sha256"],
                "operation_key": str(uuid4()),
                "operator_label": "roles-lab",
                "reason_code": "pedagogical_sequence",
                "confirm_database": "aulas_roles_lab",
            }
            try:
                async with factory() as session:
                    receipt = await apply_editorial_reorder(session, graph, **request)
                assert receipt["db_actor"] == "aulas_owner"
                assert receipt["db_login"] == "aulas_migrator"
                assert receipt["changed_entities"] == 2 and not receipt["replayed"]
                async with factory() as session:
                    replay = await apply_editorial_reorder(session, graph, **request)
                assert replay == {**receipt, "replayed": True}
            finally:
                await connection.rollback()
        after = await connection.scalar(
            select(func.count()).select_from(EditorialReorderEvent)
        )
        assert after == before
    await dispose_engine()
    print("Reordenação auditada e retry pelo migrador aprovados; ensaio revertido.")


if __name__ == "__main__":
    asyncio.run(main())
