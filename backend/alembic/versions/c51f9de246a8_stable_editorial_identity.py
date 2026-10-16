"""40B.2b.2: immutable entity keys; leave IDs, content and historical results intact."""

import json
from uuid import UUID, uuid5

import sqlalchemy as sa

from alembic import op

revision = "c51f9de246a8"
down_revision = "b40e8cd13597"
branch_labels = None
depends_on = None

# Frozen migration recipe, intentionally not imported from application code.
NAMESPACE = UUID("605c62ea-e8be-4cb1-a7ce-436f7bd706f0")
TABLES = (
    "course_review_question",
    "exercise",
    "lesson_media",
    "transcript_cue",
    "vocab_item",
    "writing_prompt",
)


def upgrade() -> None:
    connection = op.get_bind()
    schema = connection.dialect.identifier_preparer.quote_schema(
        connection.scalar(sa.text("SELECT current_schema()"))
    )
    for table in TABLES:
        op.add_column(table, sa.Column("editorial_key", sa.Uuid(as_uuid=False), nullable=True))
        if table == "course_review_question":
            query = """SELECT q.id, c.slug, u.slug, q.position
                FROM course_review_question q JOIN course_review r ON r.id=q.review_id
                JOIN course_unit u ON u.id=r.unit_id JOIN course c ON c.id=u.course_id"""
        elif table == "transcript_cue":
            query = """SELECT q.id, c.slug, l.number, m.position, q.position
                FROM transcript_cue q JOIN lesson_media m ON m.id=q.media_id
                JOIN lesson l ON l.id=m.lesson_id JOIN course c ON c.id=l.course_id"""
        else:
            field = "term" if table == "vocab_item" else "position"
            query = f"""SELECT q.id, c.slug, l.number, q.{field}
                FROM {table} q JOIN lesson l ON l.id=q.lesson_id
                JOIN course c ON c.id=l.course_id"""
        rows = connection.execute(sa.text(query))
        while batch := rows.fetchmany(500):
            values = [
                {
                    "id": row[0],
                    "key": str(
                        uuid5(
                            NAMESPACE,
                            json.dumps(
                                [table, *row[1:]], ensure_ascii=False, separators=(",", ":")
                            ),
                        )
                    ),
                }
                for row in batch
            ]
            connection.execute(
                sa.text(f"UPDATE {table} SET editorial_key=CAST(:key AS uuid) WHERE id=:id"), values
            )
        op.alter_column(
            table,
            "editorial_key",
            existing_type=sa.Uuid(as_uuid=False),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        )
        op.create_unique_constraint(f"uq_{table}_editorial_key", table, ["editorial_key"])
    op.execute(f"""CREATE FUNCTION {schema}.aulas_keep_editorial_identity() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog, {schema} AS $$
      BEGIN
        IF NEW.editorial_key IS DISTINCT FROM OLD.editorial_key THEN
          RAISE EXCEPTION 'editorial identity is immutable' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
      END $$""")
    op.execute(f"REVOKE ALL ON FUNCTION {schema}.aulas_keep_editorial_identity() FROM PUBLIC")
    for table in TABLES:
        op.execute(f"""CREATE TRIGGER {table}_immutable_identity
          BEFORE UPDATE OF editorial_key ON {schema}.{table}
          FOR EACH ROW EXECUTE FUNCTION {schema}.aulas_keep_editorial_identity()""")


def downgrade() -> None:
    # Losing a persisted key could reassign a reordered entity on re-upgrade.
    # Roll back application code instead; the added deferred columns can remain.
    for table in TABLES:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")):
            raise RuntimeError("Preserve editorial identities: downgrade requires empty tables.")
    for table in TABLES:
        op.execute(f"DROP TRIGGER {table}_immutable_identity ON {table}")
        op.drop_constraint(f"uq_{table}_editorial_key", table, type_="unique")
        op.drop_column(table, "editorial_key")
    op.execute("DROP FUNCTION aulas_keep_editorial_identity()")
