"""40B.2a: private immutable snapshots, no invented legacy backfill."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b40e8cd13597"
down_revision = "a39d7bc02486"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_content_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_attempt_id", sa.Integer(), sa.ForeignKey("exercise_attempt.id", ondelete="CASCADE"), unique=True),
        sa.Column("practice_item_id", sa.Integer(), sa.ForeignKey("practice_session_item.id", ondelete="CASCADE"), unique=True),
        sa.Column("writing_feedback_id", sa.Integer(), sa.ForeignKey("writing_feedback.id", ondelete="CASCADE"), unique=True),
        sa.Column("speaking_attempt_id", sa.Integer(), sa.ForeignKey("speaking_attempt.id", ondelete="CASCADE"), unique=True),
        sa.Column("checkpoint_attempt_id", sa.Integer(), sa.ForeignKey("course_review_attempt.id", ondelete="CASCADE"), unique=True),
        sa.Column("schema_version", sa.String(10), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("schema_version = '1.0'", name="ck_snapshot_schema"),
        sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_snapshot_hash"),
        sa.CheckConstraint("jsonb_typeof(content) = 'object' AND octet_length(content::text) <= 262144", name="ck_snapshot_content"),
        sa.CheckConstraint("num_nonnulls(exercise_attempt_id, practice_item_id, writing_feedback_id, speaking_attempt_id, checkpoint_attempt_id) = 1", name="ck_snapshot_one_parent"),
    )
    op.create_index("ix_snapshot_user_created", "evidence_content_snapshot", ["user_id", "created_at", "id"])
    connection = op.get_bind()
    schema = connection.dialect.identifier_preparer.quote_schema(
        connection.scalar(sa.text("SELECT current_schema()")))
    op.execute(f"""CREATE FUNCTION {schema}.aulas_check_content_snapshot() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog, {schema} AS $$
    DECLARE owner_id integer;
    BEGIN
      IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'content snapshot is immutable' USING ERRCODE = '23514';
      END IF;
      IF NEW.exercise_attempt_id IS NOT NULL THEN
        SELECT user_id INTO owner_id FROM exercise_attempt WHERE id=NEW.exercise_attempt_id;
      ELSIF NEW.practice_item_id IS NOT NULL THEN
        SELECT p.user_id INTO owner_id FROM practice_session p
          JOIN practice_session_item i ON i.practice_session_id=p.id WHERE i.id=NEW.practice_item_id;
      ELSIF NEW.writing_feedback_id IS NOT NULL THEN
        SELECT user_id INTO owner_id FROM writing_feedback WHERE id=NEW.writing_feedback_id;
      ELSIF NEW.speaking_attempt_id IS NOT NULL THEN
        SELECT user_id INTO owner_id FROM speaking_attempt WHERE id=NEW.speaking_attempt_id;
      ELSIF NEW.checkpoint_attempt_id IS NOT NULL THEN
        SELECT user_id INTO owner_id FROM course_review_attempt WHERE id=NEW.checkpoint_attempt_id;
      END IF;
      IF owner_id IS DISTINCT FROM NEW.user_id OR owner_id IS NULL THEN
        RAISE EXCEPTION 'content snapshot owner mismatch' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute(f"REVOKE ALL ON FUNCTION {schema}.aulas_check_content_snapshot() FROM PUBLIC")
    op.execute(f"""CREATE TRIGGER evidence_content_snapshot_immutable
      BEFORE INSERT OR UPDATE ON {schema}.evidence_content_snapshot
      FOR EACH ROW EXECUTE FUNCTION {schema}.aulas_check_content_snapshot()""")
    op.execute("""DO $$ BEGIN
      IF current_user = 'aulas_owner' AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_runtime') THEN
        GRANT SELECT, INSERT ON evidence_content_snapshot TO aulas_runtime;
        GRANT USAGE ON SEQUENCE evidence_content_snapshot_id_seq TO aulas_runtime;
        GRANT SELECT ON evidence_content_snapshot TO aulas_backup;
      END IF;
    END $$""")


def downgrade() -> None:
    # Empty-schema rehearsal is reversible; never discard captured history.
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM evidence_content_snapshot)")):
        raise RuntimeError("Preserve snapshots: downgrade requires an empty isolated table.")
    op.drop_table("evidence_content_snapshot")
    op.execute("DROP FUNCTION aulas_check_content_snapshot()")
