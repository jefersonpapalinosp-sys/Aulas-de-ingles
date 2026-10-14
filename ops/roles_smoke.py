"""Sonda exclusivamente no servidor sintético de papéis; nunca aceita alvo de estudo."""

import json
import sys
import tempfile

from ops import recovery, roles
from ops.recovery_archive import RecoveryError, require


def forbidden(info, role, statement):
    try:
        roles.sql(info, "\\set VERBOSITY verbose\n" + statement, role)
    except RecoveryError as exc:
        stderr = getattr(exc.__cause__, "stderr", b"")
        require(b"42501" in stderr, "Recusa não foi por privilégio insuficiente.")
    else:
        raise RecoveryError("Operação proibida foi permitida no laboratório.")


def main():
    info = roles.target("lab")
    for role in roles.NAMES[1:]:
        flags = json.loads(
            roles.sql(
                info,
                """
          SELECT json_build_array(rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls)
          FROM pg_roles WHERE rolname=current_user
        """,
                role,
            )
        )
        require(flags == [False] * 5, "Papel com poderes globais.")
    for role in ("aulas_runtime", "aulas_worker", "aulas_backup"):
        for statement in (
            "CREATE TABLE public.forbidden_role_probe (id integer)",
            "ALTER TABLE app_user ADD COLUMN forbidden_role_probe integer",
            "CREATE ROLE forbidden_role_probe",
            "CREATE DATABASE forbidden_role_probe",
            "SET ROLE aulas_owner",
            "TRUNCATE app_user CASCADE",
        ):
            forbidden(info, role, statement)
    forbidden(info, "aulas_runtime", "UPDATE lesson SET title=title")
    forbidden(info, "aulas_runtime", "UPDATE alembic_version SET version_num=version_num")
    forbidden(info, "aulas_runtime", "UPDATE review_event SET quality=quality")
    forbidden(info, "aulas_runtime", "DELETE FROM review_event")
    forbidden(info, "aulas_worker", "SELECT * FROM auth_rate_bucket")
    forbidden(info, "aulas_backup", "DELETE FROM app_user")
    forbidden(info, "aulas_worker", "SELECT password_hash FROM app_user")
    forbidden(info, "aulas_worker", "DELETE FROM transcription_job")
    forbidden(info, "aulas_worker", "UPDATE speaking_attempt SET status=status")
    roles.sql(
        info,
        """
      BEGIN;
      INSERT INTO app_user(email,password_hash,display_name)
      VALUES ('role-probe@example.invalid','!disabled!','synthetic');
      UPDATE app_user SET display_name='synthetic updated' WHERE email='role-probe@example.invalid';
      DELETE FROM app_user WHERE email='role-probe@example.invalid';
      ROLLBACK;
    """,
        "aulas_runtime",
    )
    roles.sql(
        info,
        "SELECT id FROM transcription_job; UPDATE transcription_job SET status=status;",
        "aulas_worker",
    )
    # Migrador realmente usa SET ROLE pelo driver e passa a guarda da conexão.
    roles.lab_run("migrator", "alembic", "upgrade", "head")
    roles.lab_run("runtime", "python", "/tools/roles_app_smoke.py")
    roles.lab_run(
        "worker",
        "python",
        "-c",
        "import asyncio; from app.services.transcription_queue import _claim_next_job; "
        "from datetime import datetime,UTC; "
        "asyncio.run(_claim_next_job(datetime.now(UTC)))",
    )
    # Backup apenas SELECT/seq; arquivo privado temporário, sem dados do aluno.
    with tempfile.TemporaryFile() as dump:
        recovery.docker(
            "exec",
            "-i",
            info[0]["Id"],
            "pg_dump",
            "-h",
            "/var/run/postgresql",
            "-U",
            "aulas_backup",
            "-d",
            info[1],
            "-Fc",
            stdout=dump,
        )
        require(dump.tell() > 0, "Dump de leitura vazio.")
        dump.seek(0)
        recovery.docker("exec", "-i", info[0]["Id"], "pg_restore", "--list", stdin=dump)
    print(
        "Papéis aprovados: 27 recusas de privilégio, DML runtime, API HTTP, worker e dump limitado."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Ensaio de papéis falhou; não liberar rollout.", file=sys.stderr)
        raise SystemExit(1) from None
