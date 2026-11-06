"""Compara privilégios efetivos com a política canônica em transação revertida no lab."""

import json

from ops import recovery, roles
from ops.recovery_archive import require

SNAPSHOT = """
WITH actors AS (
  SELECT unnest(ARRAY['aulas_runtime','aulas_worker','aulas_backup']) AS actor
), relations AS (
  SELECT c.oid,c.relname,c.relkind FROM pg_class c
  JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public' AND c.relkind IN ('r','p','S')
), privileges AS (
  SELECT actor,'table' kind,relname object,'' col,p privilege,
    has_table_privilege(actor,oid,p) allowed
  FROM actors CROSS JOIN relations CROSS JOIN unnest(ARRAY[
    'SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p
  WHERE relkind IN ('r','p')
  UNION ALL
  SELECT actor,'column',relname,a.attname,p,has_column_privilege(actor,r.oid,a.attnum,p)
  FROM actors CROSS JOIN relations r JOIN pg_attribute a ON a.attrelid=r.oid
  CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','REFERENCES']) p
  WHERE relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
  UNION ALL
  SELECT actor,'sequence',relname,'',p,has_sequence_privilege(actor,oid,p)
  FROM actors CROSS JOIN relations CROSS JOIN unnest(ARRAY['SELECT','UPDATE','USAGE']) p
  WHERE relkind='S'
  UNION ALL
  SELECT actor,'function',p.oid::regprocedure::text,'','EXECUTE',
    has_function_privilege(actor,p.oid,'EXECUTE')
  FROM actors CROSS JOIN pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public'
)
SELECT jsonb_agg(to_jsonb(privileges) ORDER BY actor,kind,object,col,privilege) AS snapshot
FROM privileges
"""


def verify_policy(info: roles.TargetInfo) -> None:
    # Somente o chamador de laboratório validado usa esta comparação. ROLLBACK
    # preserva a divergência para diagnóstico, em vez de corrigi-la silenciosamente.
    policy = (recovery.ROOT / "ops/roles_policy.sql").read_text()
    result = roles.sql(
        info,
        "\\set QUIET 1\nBEGIN;\n"
        "CREATE TEMP TABLE policy_before ON COMMIT DROP AS "
        + SNAPSHOT
        + ";\n"
        + policy
        + "\nSELECT to_json((SELECT snapshot FROM policy_before) = ("
        + SNAPSHOT
        + "));\nROLLBACK;",
    )
    require(json.loads(result) is True, "Privilégios efetivos divergem da política canônica.")
