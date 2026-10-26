-- Alvo validado pelo orquestrador; papéis provisionados sem trocar senhas existentes.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM aulas_runtime, aulas_worker, aulas_backup;
GRANT USAGE ON SCHEMA public TO aulas_runtime, aulas_worker, aulas_backup;
ALTER SCHEMA public OWNER TO aulas_owner;
-- Apenas este schema, nunca REASSIGN OWNED de um administrador global.
DO $$
DECLARE obj record;
BEGIN
  FOR obj IN SELECT c.relname, c.relkind FROM pg_class c
    JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relkind IN ('r','p','S')
    ORDER BY CASE WHEN c.relkind='S' THEN 1 ELSE 0 END
  LOOP
    EXECUTE format('ALTER %s public.%I OWNER TO aulas_owner',
      CASE WHEN obj.relkind='S' THEN 'SEQUENCE' ELSE 'TABLE' END, obj.relname);
  END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aulas_runtime, aulas_worker, aulas_backup;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM aulas_runtime, aulas_worker, aulas_backup;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO aulas_runtime, aulas_backup;
-- Audit identifies an operational actor, not a student-facing resource.
DO $$ BEGIN
  IF to_regclass('public.editorial_archive_event') IS NOT NULL THEN
    REVOKE ALL ON editorial_archive_event FROM aulas_runtime, aulas_worker;
  END IF;
  IF to_regclass('public.editorial_reorder_event') IS NOT NULL THEN
    REVOKE ALL ON editorial_reorder_event FROM aulas_runtime, aulas_worker;
  END IF;
END $$;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO aulas_backup;
GRANT INSERT, UPDATE, DELETE ON
  app_user, refresh_session, lesson_progress, study_session_progress, step_progress,
  study_plan, skill_evidence, practice_session, practice_session_item, exercise_attempt,
  review_card, review_item, writing_draft, writing_revision, writing_feedback,
  notebook_entry, speaking_attempt, transcription_job, media_progress, course_review_attempt
TO aulas_runtime;
-- Sprint 38: recibos só podem ser inseridos/lidos pelo runtime; cascatas
-- de exclusão da conta/item são executadas pelo PostgreSQL.
DO $$ BEGIN
  IF to_regclass('public.review_event') IS NOT NULL THEN
    GRANT INSERT ON review_event TO aulas_runtime;
    GRANT USAGE ON SEQUENCE review_event_id_seq TO aulas_runtime;
    GRANT INSERT, UPDATE, DELETE ON auth_rate_bucket TO aulas_runtime;
  END IF;
END $$;
-- Sprint 39A: âncoras, recibos e intervalos são append-only no runtime.
DO $$ BEGIN
  IF to_regclass('public.study_activity_session') IS NOT NULL THEN
    GRANT INSERT ON study_activity_session, study_activity_event, study_active_interval TO aulas_runtime;
    GRANT USAGE ON SEQUENCE study_activity_event_id_seq, study_active_interval_id_seq TO aulas_runtime;
  END IF;
END $$;
DO $$
DECLARE seq text; tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY[
    'app_user','refresh_session','lesson_progress','study_session_progress','step_progress',
    'study_plan','skill_evidence','practice_session','practice_session_item','exercise_attempt',
    'review_card','review_item','writing_draft','writing_revision','writing_feedback',
    'notebook_entry','speaking_attempt','transcription_job','media_progress','course_review_attempt'
  ] LOOP
    seq := pg_get_serial_sequence(format('public.%I',tbl),'id');
    IF seq IS NOT NULL THEN
      EXECUTE format('GRANT USAGE ON SEQUENCE %s TO aulas_runtime',seq);
    END IF;
  END LOOP;
END $$;
GRANT SELECT ON transcription_job, speaking_attempt, transcript_cue TO aulas_worker;
GRANT UPDATE ON transcription_job TO aulas_worker;
-- Sprint 39F: o consumo sobrevive à exclusão de resultados. Só owner apaga diretamente.
DO $$ BEGIN
  IF to_regclass('public.assist_reservation') IS NOT NULL THEN
    GRANT SELECT, INSERT, UPDATE ON assist_reservation TO aulas_runtime;
    GRANT USAGE ON SEQUENCE assist_reservation_id_seq TO aulas_runtime;
    GRANT SELECT, UPDATE ON assist_reservation TO aulas_worker;
  END IF;
END $$;
-- Tabelas futuras não recebem escrita automaticamente; migration deve declarar DML.
DO $$ BEGIN
  IF to_regclass('public.evidence_content_snapshot') IS NOT NULL THEN
    GRANT INSERT ON evidence_content_snapshot TO aulas_runtime;
    GRANT USAGE ON SEQUENCE evidence_content_snapshot_id_seq TO aulas_runtime;
  END IF;
END $$;
DO $$ BEGIN
  IF to_regprocedure('public.aulas_speaking_expected_text(integer,integer)') IS NOT NULL THEN
    GRANT EXECUTE ON FUNCTION public.aulas_speaking_expected_text(integer, integer)
      TO aulas_worker;
  END IF;
END $$;
DO $$ BEGIN
  IF to_regclass('public.worker_heartbeat') IS NOT NULL THEN
    GRANT SELECT, INSERT, UPDATE ON worker_heartbeat TO aulas_worker;
    GRANT EXECUTE ON FUNCTION public.aulas_retention_batch(text, integer, boolean) TO aulas_worker;
  END IF;
END $$;
-- Sprint 40C: a API cria o recibo/tarefas e apaga a conta; o worker apenas
-- conclui a remoção idempotente das chaves opacas de áudio.
DO $$ BEGIN
  IF to_regclass('public.account_deletion_job') IS NOT NULL THEN
    GRANT SELECT, INSERT, UPDATE ON account_deletion_job TO aulas_runtime;
    GRANT SELECT, INSERT, UPDATE, DELETE ON account_deletion_file TO aulas_runtime;
    GRANT USAGE ON SEQUENCE account_deletion_file_id_seq TO aulas_runtime;
    GRANT SELECT, UPDATE ON account_deletion_job TO aulas_worker;
    GRANT SELECT, UPDATE, DELETE ON account_deletion_file TO aulas_worker;
  END IF;
END $$;
-- DB-45: a API cria/encerra diálogos e insere turnos; só altera a avaliação
-- humana. O worker preenche o resultado do turno e nunca apaga. Cascatas são
-- do PostgreSQL. Espelho do bloco da migration e3a1c7d9b250.
DO $$ BEGIN
  IF to_regclass('public.dialogue_turn') IS NOT NULL THEN
    GRANT INSERT, DELETE ON speaking_dialogue TO aulas_runtime;
    GRANT UPDATE (state, ended_at, provider_name) ON speaking_dialogue TO aulas_runtime;
    GRANT INSERT ON dialogue_turn TO aulas_runtime;
    GRANT UPDATE (human_rating) ON dialogue_turn TO aulas_runtime;
    GRANT USAGE ON SEQUENCE speaking_dialogue_id_seq, dialogue_turn_id_seq TO aulas_runtime;
    GRANT SELECT ON speaking_dialogue TO aulas_worker;
    GRANT UPDATE (state, ended_at) ON speaking_dialogue TO aulas_worker;
    GRANT SELECT, INSERT ON dialogue_turn TO aulas_worker;
    GRANT UPDATE (state, transcription_job_id, transcript, checks, partner_text, hints,
                  confidence, fallback, cost_microusd, error_code, completed_at)
      ON dialogue_turn TO aulas_worker;
    GRANT USAGE ON SEQUENCE dialogue_turn_id_seq TO aulas_worker;
  END IF;
END $$;
ALTER DEFAULT PRIVILEGES FOR ROLE aulas_owner IN SCHEMA public
  GRANT SELECT ON TABLES TO aulas_runtime, aulas_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE aulas_owner IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO aulas_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE aulas_owner
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
