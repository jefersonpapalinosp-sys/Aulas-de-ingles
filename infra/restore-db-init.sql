-- Destino exclusivo e vazio; pg_restore usa o dono limitado, nunca o administrador.
CREATE ROLE aulas_restore LOGIN PASSWORD 'restore_disposable_only'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE aulas_ingles_restore OWNER aulas_restore;
COMMENT ON DATABASE aulas_ingles_restore IS 'aulas-ingles:recovery-target:v1';
REVOKE ALL ON DATABASE aulas_ingles_restore FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE aulas_ingles_restore TO aulas_restore;
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;
