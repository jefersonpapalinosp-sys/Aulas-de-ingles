#!/bin/sh
set -eu

# Executado pelo entrypoint oficial apenas quando o volume do PostgreSQL está
# vazio. Segredos chegam por variáveis e seguem por stdin/psql variables; nunca
# são escritos no log ou colocados na linha de comando do servidor.
: "${POSTGRES_USER:?POSTGRES_USER obrigatório}"
: "${POSTGRES_DB:?POSTGRES_DB obrigatório}"
: "${AULAS_MIGRATOR_PASSWORD:?AULAS_MIGRATOR_PASSWORD obrigatório}"
: "${AULAS_RUNTIME_PASSWORD:?AULAS_RUNTIME_PASSWORD obrigatório}"
: "${AULAS_WORKER_PASSWORD:?AULAS_WORKER_PASSWORD obrigatório}"
: "${AULAS_BACKUP_PASSWORD:?AULAS_BACKUP_PASSWORD obrigatório}"

psql -X --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=database_name="$POSTGRES_DB" \
  --set=migrator_password="$AULAS_MIGRATOR_PASSWORD" \
  --set=runtime_password="$AULAS_RUNTIME_PASSWORD" \
  --set=worker_password="$AULAS_WORKER_PASSWORD" \
  --set=backup_password="$AULAS_BACKUP_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE aulas_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_owner') \gexec

SELECT format(
  'CREATE ROLE aulas_migrator LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'migrator_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_migrator') \gexec

SELECT format(
  'CREATE ROLE aulas_runtime LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'runtime_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_runtime') \gexec

SELECT format(
  'CREATE ROLE aulas_worker LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'worker_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_worker') \gexec

SELECT format(
  'CREATE ROLE aulas_backup LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'backup_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_backup') \gexec

COMMENT ON ROLE aulas_owner IS 'aulas-ingles:role-v1';
COMMENT ON ROLE aulas_migrator IS 'aulas-ingles:role-v1';
COMMENT ON ROLE aulas_runtime IS 'aulas-ingles:role-v1';
COMMENT ON ROLE aulas_worker IS 'aulas-ingles:role-v1';
COMMENT ON ROLE aulas_backup IS 'aulas-ingles:role-v1';

REVOKE ALL ON DATABASE :"database_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database_name"
  TO aulas_owner, aulas_migrator, aulas_runtime, aulas_worker, aulas_backup;
GRANT aulas_owner TO aulas_migrator WITH ADMIN FALSE;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO aulas_owner;
SQL
