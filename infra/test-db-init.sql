-- Credenciais exclusivas e públicas de uma base descartável em loopback.
-- O administrador só provisiona; Alembic, seed e pytest usam aulas_test.
CREATE ROLE aulas_test LOGIN PASSWORD 'aulas_test_only'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE aulas_ingles_test OWNER aulas_test;
COMMENT ON DATABASE aulas_ingles_test IS 'aulas-ingles:disposable-test:v1';
REVOKE ALL ON DATABASE aulas_ingles_test FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE aulas_ingles_test TO aulas_test;
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;

-- Sentinela sintética de isolamento. Não é a base do aluno.
CREATE DATABASE aulas_test_sentinel OWNER aulas_test_admin;
REVOKE ALL ON DATABASE aulas_test_sentinel FROM PUBLIC;
\connect aulas_test_sentinel
CREATE TABLE isolation_sentinel (id integer PRIMARY KEY, value text NOT NULL);
INSERT INTO isolation_sentinel VALUES (1, 'preserve-this-synthetic-record');
