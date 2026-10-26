"""DB-46: retenção dos textos do turno de diálogo

`transcript`, `partner_text` e `hints` seguem `ASSIST_RETENTION_DAYS` pelo
`expires_at` que o turno já guarda. O escopo novo da função de retenção é o
único que **anonimiza** em vez de apagar a linha: o texto do aluno vence, e a
evidência de que ele praticou fica. Apagar o turno inteiro levaria junto
`checks`, custo e avaliação humana — justamente o que o gate do IA-48 precisa e
o que o aluno vê como histórico de prática.

A função é substituída inteira (`CREATE OR REPLACE`) porque plpgsql não aceita
acrescentar um ramo; os quatro escopos anteriores seguem idênticos.

Revision ID: b7e5f1c38a42
Revises: f4c2e8a71b30
Create Date: 2026-10-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7e5f1c38a42"
down_revision: str | None = "f4c2e8a71b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RETENTION_SQL = """
CREATE OR REPLACE FUNCTION public.aulas_retention_batch(kind text, batch_size integer, apply boolean)
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
  ELSIF kind = 'dialogues' THEN
    -- Único escopo que ANONIMIZA em vez de apagar a linha: o texto do aluno
    -- vence, a evidência de que ele praticou fica. `checks`, custo, avaliação
    -- humana e posição permanecem -- é com eles que o gate do IA-48 trabalha
    -- e é com eles que o aluno vê seu próprio histórico de prática.
    IF apply THEN
      WITH candidates AS (SELECT id FROM public.dialogue_turn
        WHERE expires_at <= now()
          AND (transcript IS NOT NULL OR partner_text IS NOT NULL OR hints <> '[]'::jsonb)
        ORDER BY expires_at, id LIMIT batch_size FOR UPDATE SKIP LOCKED)
      UPDATE public.dialogue_turn
        SET transcript=NULL, partner_text=NULL, hints='[]'::jsonb
        WHERE id IN (SELECT id FROM candidates);
      GET DIAGNOSTICS affected = ROW_COUNT;
    ELSE
      SELECT count(*) INTO affected FROM (SELECT id FROM public.dialogue_turn
        WHERE expires_at <= now()
          AND (transcript IS NOT NULL OR partner_text IS NOT NULL OR hints <> '[]'::jsonb)
        ORDER BY expires_at, id LIMIT batch_size) t;
    END IF;
  ELSE
    RAISE EXCEPTION 'invalid retention scope';
  END IF;
  RETURN affected;
END $$;
"""

ANTERIOR_SQL = """
CREATE OR REPLACE FUNCTION public.aulas_retention_batch(kind text, batch_size integer, apply boolean)
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
    op.execute(RETENTION_SQL)


def downgrade() -> None:
    """Volta a função sem o escopo `dialogues`.

    Nada é apagado nem restaurado: o que já foi anonimizado não volta, porque
    o texto não existe mais em lugar nenhum — é o ponto da retenção.
    """
    op.execute(ANTERIOR_SQL)
