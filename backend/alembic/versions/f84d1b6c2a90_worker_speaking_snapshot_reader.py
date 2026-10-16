"""Allow the STT worker to read only the captured cue it must compare.

Revision ID: f84d1b6c2a90
Revises: e73c1a9b40d2
"""

from alembic import op

revision = "f84d1b6c2a90"
down_revision = "e73c1a9b40d2"
branch_labels = None
depends_on = None

FUNCTION = "public.aulas_speaking_expected_text(integer, integer)"


def upgrade() -> None:
    # The worker remains unable to SELECT the snapshot table. This fixed,
    # ownership-scoped projection exposes only the English cue associated
    # with one speaking attempt, not writing/exercise/checkpoint content.
    op.execute(
        """
        CREATE FUNCTION public.aulas_speaking_expected_text(
          requested_attempt_id integer,
          requested_user_id integer
        ) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT CASE
            WHEN snapshot.content->>'kind' = 'speaking'
            THEN NULLIF(btrim(snapshot.content->>'text_en'), '')
          END
          FROM public.evidence_content_snapshot AS snapshot
          WHERE snapshot.speaking_attempt_id = requested_attempt_id
            AND snapshot.user_id = requested_user_id
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {FUNCTION} FROM PUBLIC")
    op.execute(
        f"""DO $$ BEGIN
          IF current_user = 'aulas_owner'
             AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_worker') THEN
            GRANT EXECUTE ON FUNCTION {FUNCTION} TO aulas_worker;
          END IF;
        END $$"""
    )


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {FUNCTION}")
