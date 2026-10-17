#!/bin/sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER obrigatório}"
: "${POSTGRES_DB:?POSTGRES_DB obrigatório}"
: "${PGPASSWORD:?PGPASSWORD obrigatório}"

count="$({
  psql -XAt --set=ON_ERROR_STOP=1 -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
SELECT count(*)
FROM pg_roles
WHERE rolname IN ('aulas_owner','aulas_migrator','aulas_runtime','aulas_worker','aulas_backup')
  AND shobj_description(oid, 'pg_authid') = 'aulas-ingles:role-v1';
SQL
} | tr -d '[:space:]')"

if [ "$count" != "5" ]; then
  echo "Papéis marcados ausentes; grants recusados." >&2
  exit 1
fi

psql -Xq --set=ON_ERROR_STOP=1 -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --file /opt/aulas/roles_policy.sql

echo "Política de grants aplicada sem exibir credenciais."
