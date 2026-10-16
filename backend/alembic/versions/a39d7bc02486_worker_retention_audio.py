"""Sprint 39G/H: retenção limitada, heartbeat e integridade durável de voz."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a39d7bc02486"
down_revision = "f28c6abe1375"
branch_labels = None
depends_on = None

# SECURITY DEFINER oferece operações fixas, não DELETE irrestrito ao worker.
# Sem SQL dinâmico, search_path fixo, limites e prazos mínimos conferidos no banco.
RETENTION_SQL = """
CREATE FUNCTION public.aulas_retention_batch(kind text, batch_size integer, apply boolean)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public AS $$
DECLARE affected integer;
BEGIN
  IF batch_size < 1 OR batch_size > 500 OR batch_size IS NULL OR apply IS NULL THEN
    RAISE EXCEPTION 'invalid retention limit';
  END IF;
  IF kind = 'transcriptions' THEN
    IF apply THEN
      WITH candidates AS (
        SELECT id FROM public.transcription_job WHERE expires_at <= now()
        ORDER BY expires_at, id LIMIT batch_size FOR UPDATE SKIP LOCKED
      ), released AS (
        UPDATE public.assist_reservation r SET state='released', reason='job_expired'
        FROM public.transcription_job j, candidates c
        WHERE j.id=c.id AND r.id=j.assist_reservation_id AND r.state='reserved'
      ) DELETE FROM public.transcription_job WHERE id IN (SELECT id FROM candidates);
      GET DIAGNOSTICS affected = ROW_COUNT;
    ELSE
      SELECT count(*) INTO affected FROM (SELECT id FROM public.transcription_job
        WHERE expires_at <= now() ORDER BY expires_at, id LIMIT batch_size) t;
    END IF;
  ELSIF kind = 'reservations' THEN
    IF apply THEN
      WITH candidates AS (SELECT id FROM public.assist_reservation
        WHERE state='reserved' AND expires_at <= now()
        ORDER BY expires_at, id LIMIT batch_size FOR UPDATE SKIP LOCKED)
      UPDATE public.assist_reservation SET state='released', reason='reservation_expired'
        WHERE id IN (SELECT id FROM candidates);
      GET DIAGNOSTICS affected = ROW_COUNT;
    ELSE
      SELECT count(*) INTO affected FROM (SELECT id FROM public.assist_reservation
        WHERE state='reserved' AND expires_at <= now()
        ORDER BY expires_at, id LIMIT batch_size) t;
    END IF;
  ELSIF kind = 'refresh' THEN
    IF apply THEN
      WITH candidates AS (SELECT id FROM public.refresh_session
        WHERE expires_at < now() - interval '7 days'
        ORDER BY expires_at, id LIMIT batch_size FOR UPDATE SKIP LOCKED)
      DELETE FROM public.refresh_session WHERE id IN (SELECT id FROM candidates);
      GET DIAGNOSTICS affected = ROW_COUNT;
    ELSE
      SELECT count(*) INTO affected FROM (SELECT id FROM public.refresh_session
        WHERE expires_at < now() - interval '7 days'
        ORDER BY expires_at, id LIMIT batch_size) t;
    END IF;
  ELSIF kind = 'pending' THEN
    IF apply THEN
      WITH candidates AS (SELECT id FROM public.speaking_attempt
        WHERE status='pending' AND storage_key IS NULL AND file_size IS NULL
          AND created_at < now() - interval '7 days'
        ORDER BY created_at, id LIMIT batch_size FOR UPDATE SKIP LOCKED)
      DELETE FROM public.speaking_attempt WHERE id IN (SELECT id FROM candidates);
      GET DIAGNOSTICS affected = ROW_COUNT;
    ELSE
      SELECT count(*) INTO affected FROM (SELECT id FROM public.speaking_attempt
        WHERE status='pending' AND storage_key IS NULL AND file_size IS NULL
          AND created_at < now() - interval '7 days'
        ORDER BY created_at, id LIMIT batch_size) t;
    END IF;
  ELSE
    RAISE EXCEPTION 'invalid retention scope';
  END IF;
  RETURN affected;
END $$;
"""


def upgrade() -> None:
    op.add_column("speaking_attempt", sa.Column("audio_sha256", sa.String(64), nullable=True))
    op.add_column(
        "speaking_attempt",
        sa.Column("integrity_state", sa.String(20), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "speaking_attempt",
        sa.Column("integrity_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_speaking_sha256",
        "speaking_attempt",
        "audio_sha256 IS NULL OR audio_sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "ck_speaking_integrity",
        "speaking_attempt",
        "integrity_state IN ('unknown','verified','missing','changed')",
    )
    op.create_index("ix_speaking_status_created", "speaking_attempt", ["status", "created_at"])
    op.create_index("ix_refresh_expiry", "refresh_session", ["expires_at"])
    op.create_table(
        "worker_heartbeat",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("maintenance_at", sa.DateTime(timezone=True)),
        sa.Column("maintenance_counts", postgresql.JSONB()),
    )
    # Legado permanece unknown/NULL; nenhum checksum é inventado na migration.
    op.execute(RETENTION_SQL)
    op.execute(
        "REVOKE ALL ON FUNCTION public.aulas_retention_batch(text, integer, boolean) FROM PUBLIC"
    )
    op.execute("""DO $$ BEGIN
      IF current_user = 'aulas_owner' AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_worker') THEN
        GRANT SELECT ON worker_heartbeat TO aulas_runtime;
        GRANT SELECT, INSERT, UPDATE ON worker_heartbeat TO aulas_worker;
        GRANT EXECUTE ON FUNCTION public.aulas_retention_batch(text, integer, boolean) TO aulas_worker;
      END IF;
    END $$""")


def downgrade() -> None:
    raise RuntimeError("Sprint 39: preserve checksums e ledger; restaure somente em base isolada.")
