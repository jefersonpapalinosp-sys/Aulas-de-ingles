"""Sprint 52: fila durável e retenção do áudio de diálogo."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d52a1b8c9001"
down_revision: str | None = "c92f4a8d710e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dialogue_audio_deletion",
        sa.Column("storage_key", sa.String(80), primary_key=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_error_code", sa.String(50)),
        sa.CheckConstraint("attempt_count >= 0", name="ck_dialogue_audio_deletion_attempts"),
    )
    op.create_index(
        "ix_dialogue_audio_deletion_next",
        "dialogue_audio_deletion",
        ["next_attempt_at", "storage_key"],
    )
    op.execute("""
    CREATE FUNCTION public.aulas_queue_dialogue_audio_delete() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    BEGIN
      -- Exclusão de conta já possui recibo e tarefa para esta mesma chave.
      IF OLD.origin = 'dialogue' AND OLD.storage_key IS NOT NULL
         AND NOT EXISTS (SELECT 1 FROM public.account_deletion_file
                         WHERE storage_key = OLD.storage_key) THEN
        INSERT INTO public.dialogue_audio_deletion(storage_key) VALUES (OLD.storage_key)
          ON CONFLICT (storage_key) DO NOTHING;
      END IF;
      RETURN OLD;
    END $$;
    """)
    op.execute("REVOKE ALL ON FUNCTION public.aulas_queue_dialogue_audio_delete() FROM PUBLIC")
    op.execute("""
    CREATE TRIGGER queue_dialogue_audio_delete BEFORE DELETE ON public.speaking_attempt
      FOR EACH ROW EXECUTE FUNCTION public.aulas_queue_dialogue_audio_delete();
    """)
    op.execute("""
    CREATE FUNCTION public.aulas_dialogue_audio_retention(batch_size integer, apply boolean)
    RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
    SET search_path = pg_catalog, public AS $$
    DECLARE affected integer;
    BEGIN
      IF batch_size IS NULL OR batch_size < 1 OR batch_size > 500 OR apply IS NULL THEN
        RAISE EXCEPTION 'invalid retention limit';
      END IF;
      IF apply THEN
        WITH candidates AS (
          SELECT a.id FROM public.speaking_attempt a
          LEFT JOIN public.dialogue_turn t ON t.speaking_attempt_id = a.id
          WHERE a.origin = 'dialogue' AND (t.id IS NULL OR t.expires_at <= now())
          ORDER BY a.id LIMIT batch_size FOR UPDATE OF a SKIP LOCKED
        ) DELETE FROM public.speaking_attempt WHERE id IN (SELECT id FROM candidates);
        GET DIAGNOSTICS affected = ROW_COUNT;
      ELSE
        SELECT count(*) INTO affected FROM (
          SELECT a.id FROM public.speaking_attempt a
          LEFT JOIN public.dialogue_turn t ON t.speaking_attempt_id = a.id
          WHERE a.origin = 'dialogue' AND (t.id IS NULL OR t.expires_at <= now())
          ORDER BY a.id LIMIT batch_size
        ) candidates;
      END IF;
      RETURN affected;
    END $$;
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION public.aulas_dialogue_audio_retention(integer, boolean) FROM PUBLIC"
    )
    op.execute("""
    DO $$ BEGIN
      IF current_user = 'aulas_owner'
         AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_worker')
         AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_runtime') THEN
        GRANT SELECT, UPDATE, DELETE ON dialogue_audio_deletion TO aulas_runtime, aulas_worker;
        GRANT EXECUTE ON FUNCTION public.aulas_dialogue_audio_retention(integer, boolean)
          TO aulas_worker;
      END IF;
    END $$;
    """)


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM dialogue_audio_deletion")):
        raise RuntimeError("Limpeza de áudio pendente; downgrade recusado.")
    op.execute("DROP TRIGGER queue_dialogue_audio_delete ON speaking_attempt")
    op.execute("DROP FUNCTION public.aulas_queue_dialogue_audio_delete()")
    op.execute("DROP FUNCTION public.aulas_dialogue_audio_retention(integer, boolean)")
    op.drop_table("dialogue_audio_deletion")
