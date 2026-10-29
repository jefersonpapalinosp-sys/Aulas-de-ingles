"""Archive receipt under the migrator identity; entire rehearsal rolls back."""

import asyncio
from uuid import uuid4

from app.core.config import get_settings
from app.db.models import EditorialArchiveEvent
from app.db.session import dispose_engine, get_engine
from app.services.editorial_archive import archive_unit
from app.services.editorial_plan import collect_unit_archive
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker


async def main() -> None:
    settings = get_settings()
    assert settings.database_purpose == "migrator" and settings.app_env == "dev"
    assert settings.database_url.endswith("@db:5432/aulas_roles_lab")
    previous_enabled = settings.editorial_archive_enabled
    settings.editorial_archive_enabled = True
    try:
        engine = get_engine()
        async with engine.connect() as connection:
            before = await connection.scalar(
                select(func.count()).select_from(EditorialArchiveEvent)
            )
            await connection.rollback()
            async with connection.begin():
                factory = async_sessionmaker(
                    connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )
                try:
                    async with factory() as session:
                        plan = await collect_unit_archive(session, "voa-level-2", "26-30")
                    request = {
                        "course_slug": "voa-level-2",
                        "unit_slug": "26-30",
                        "expected_catalog_sha256": plan["catalog_sha256"],
                        "operation_key": str(uuid4()),
                        "operator_label": "roles-lab",
                        "reason_code": "editorial_review",
                        "confirm_database": plan["database"],
                    }
                    async with factory() as session:
                        receipt = await archive_unit(session, **request)
                    assert receipt["db_actor"] == "aulas_owner"
                    assert receipt["db_login"] == "aulas_migrator"
                    assert receipt["after_status"] == "archived" and not receipt["replayed"]
                    async with factory() as session:
                        replay = await archive_unit(session, **request)
                    assert replay == {**receipt, "replayed": True}
                finally:
                    await connection.rollback()
            after = await connection.scalar(
                select(func.count()).select_from(EditorialArchiveEvent)
            )
            assert after == before
    finally:
        settings.editorial_archive_enabled = previous_enabled
        await dispose_engine()
    print(
        "Arquivamento auditado e retry pelo migrador aprovados; ensaio revertido por rollback."
    )


if __name__ == "__main__":
    asyncio.run(main())
