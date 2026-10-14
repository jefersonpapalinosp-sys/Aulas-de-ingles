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
-- Tabelas futuras não recebem escrita automaticamente; migration deve declarar DML.
ALTER DEFAULT PRIVILEGES FOR ROLE aulas_owner IN SCHEMA public
  GRANT SELECT ON TABLES TO aulas_runtime, aulas_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE aulas_owner IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO aulas_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE aulas_owner
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
