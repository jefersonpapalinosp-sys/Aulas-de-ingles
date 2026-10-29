"""Sonda exclusivamente no servidor sintético de papéis; nunca aceita alvo de estudo."""

import json
import sys
import tempfile

from ops import recovery, roles
from ops.recovery_archive import RecoveryError, require


def forbidden(info: roles.TargetInfo, role: str, statement: str) -> None:
    try:
        roles.sql(info, "\\set VERBOSITY verbose\n" + statement, role)
    except RecoveryError as exc:
        stderr = getattr(exc.__cause__, "stderr", b"")
        require(
            isinstance(stderr, bytes) and b"42501" in stderr,
            "Recusa não foi por privilégio insuficiente.",
        )
    else:
        raise RecoveryError("Operação proibida foi permitida no laboratório.")


def main() -> None:
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
    for table in (
        "course_review_question",
        "exercise",
        "lesson_media",
        "transcript_cue",
        "vocab_item",
        "writing_prompt",
    ):
        roles.sql(info, f"SELECT editorial_key FROM {table} LIMIT 1", "aulas_runtime")
        for role in ("aulas_runtime", "aulas_worker", "aulas_backup"):
            forbidden(info, role, f"UPDATE {table} SET editorial_key=gen_random_uuid()")
    forbidden(info, "aulas_runtime", "UPDATE alembic_version SET version_num=version_num")
    forbidden(info, "aulas_runtime", "UPDATE review_event SET quality=quality")
    forbidden(info, "aulas_runtime", "DELETE FROM review_event")
    forbidden(info, "aulas_runtime", "UPDATE evidence_content_snapshot SET content=content")
    forbidden(info, "aulas_runtime", "DELETE FROM evidence_content_snapshot")
    forbidden(info, "aulas_worker", "SELECT * FROM evidence_content_snapshot")
    forbidden(
        info,
        "aulas_runtime",
        "SELECT public.aulas_speaking_expected_text(1,1)",
    )
    forbidden(
        info,
        "aulas_backup",
        "SELECT public.aulas_speaking_expected_text(1,1)",
    )
    roles.sql(
        info,
        "SELECT public.aulas_speaking_expected_text(1,1)",
        "aulas_worker",
    )
    for role in ("aulas_runtime", "aulas_worker"):
        forbidden(info, role, "SELECT * FROM editorial_archive_event")
        forbidden(info, role, "INSERT INTO editorial_archive_event DEFAULT VALUES")
    for role in ("aulas_runtime", "aulas_worker", "aulas_backup"):
        forbidden(info, role, "DELETE FROM editorial_archive_event")
        forbidden(info, role, "UPDATE editorial_archive_event SET impact=impact")
    roles.sql(info, "SELECT count(*) FROM editorial_archive_event", "aulas_backup")
    for role in ("aulas_runtime", "aulas_worker"):
        forbidden(info, role, "SELECT * FROM editorial_reorder_event")
        forbidden(info, role, "INSERT INTO editorial_reorder_event DEFAULT VALUES")
    for role in ("aulas_runtime", "aulas_worker", "aulas_backup"):
        forbidden(info, role, "DELETE FROM editorial_reorder_event")
        forbidden(info, role, "UPDATE editorial_reorder_event SET impact=impact")
    roles.sql(info, "SELECT count(*) FROM editorial_reorder_event", "aulas_backup")
    for table in (
        "study_activity_session",
        "study_activity_event",
        "study_active_interval",
    ):
        forbidden(info, "aulas_runtime", f"DELETE FROM {table}")
        forbidden(info, "aulas_runtime", f"UPDATE {table} SET user_id=user_id")
        forbidden(info, "aulas_worker", f"SELECT * FROM {table}")
    forbidden(info, "aulas_worker", "SELECT * FROM auth_rate_bucket")
    forbidden(info, "aulas_backup", "DELETE FROM app_user")
    forbidden(info, "aulas_worker", "SELECT password_hash FROM app_user")
    forbidden(info, "aulas_worker", "DELETE FROM transcription_job")
    forbidden(info, "aulas_runtime", "DELETE FROM assist_reservation")
    forbidden(info, "aulas_worker", "DELETE FROM assist_reservation")
    forbidden(info, "aulas_worker", "INSERT INTO assist_reservation DEFAULT VALUES")
    forbidden(info, "aulas_worker", "UPDATE speaking_attempt SET status=status")
    forbidden(info, "aulas_worker", "DELETE FROM refresh_session")
    forbidden(info, "aulas_worker", "UPDATE skill_evidence SET score=score")
    forbidden(info, "aulas_worker", "DELETE FROM skill_evidence")
    forbidden(info, "aulas_worker", "UPDATE review_item SET due_at=due_at")
    forbidden(info, "aulas_worker", "DELETE FROM review_item")
    forbidden(info, "aulas_worker", "SELECT * FROM exercise_answer")
    forbidden(info, "aulas_worker", "SELECT prompt, answer FROM review_item")
    roles.sql(
        info,
        "SELECT id FROM vocab_item LIMIT 1; SELECT id FROM skill_evidence LIMIT 1",
        "aulas_worker",
    )
    forbidden(info, "aulas_runtime", "DELETE FROM account_deletion_job")
    forbidden(info, "aulas_worker", "INSERT INTO account_deletion_job DEFAULT VALUES")
    # DB-45: fora de human_rating, a API não altera turnos; o worker nunca apaga
    # nem avalia; o backup só lê.
    for statement in (
        "DELETE FROM dialogue_turn",
        "UPDATE dialogue_turn SET transcript=transcript",
        "UPDATE dialogue_turn SET check_details=check_details",
        "UPDATE dialogue_turn SET partner_text=partner_text",
        "UPDATE dialogue_turn SET state=state",
        "UPDATE dialogue_turn SET cost_microusd=cost_microusd",
        "UPDATE speaking_dialogue SET user_id=user_id",
        "UPDATE speaking_dialogue SET turn_limit=turn_limit",
    ):
        forbidden(info, "aulas_runtime", statement)
    for statement in (
        "DELETE FROM dialogue_turn",
        "DELETE FROM speaking_dialogue",
        "INSERT INTO speaking_dialogue DEFAULT VALUES",
        "UPDATE dialogue_turn SET human_rating=human_rating",
        "UPDATE dialogue_turn SET user_id=user_id",
        "UPDATE speaking_dialogue SET mode=mode",
    ):
        forbidden(info, "aulas_worker", statement)
    forbidden(info, "aulas_backup", "INSERT INTO dialogue_turn DEFAULT VALUES")
    roles.sql(info, "UPDATE dialogue_turn SET human_rating=human_rating", "aulas_runtime")
    roles.sql(
        info,
        "UPDATE dialogue_turn SET state=state, checks=checks, hints=hints; "
        "UPDATE speaking_dialogue SET state=state; SELECT count(*) FROM speaking_dialogue",
        "aulas_worker",
    )
    roles.sql(info, "SELECT count(*) FROM dialogue_turn", "aulas_backup")
    forbidden(info, "aulas_runtime", "SELECT public.aulas_retention_batch('refresh',1,true)")
    forbidden(info, "aulas_backup", "SELECT public.aulas_retention_batch('pending',1,true)")
    forbidden(info, "aulas_runtime", "UPDATE worker_heartbeat SET seen_at=seen_at")
    roles.sql(
        info,
        "SELECT public.aulas_retention_batch('transcriptions',1,false); "
        "SELECT public.aulas_retention_batch('refresh',1,false); "
        "SELECT name FROM worker_heartbeat",
        "aulas_worker",
    )
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
        """
      BEGIN;
      INSERT INTO account_deletion_job(operation_key,state,file_count,deleted_file_count)
      VALUES ('f7c88768-32b7-44eb-a577-43e382fc2358','cleanup_pending',1,0);
      INSERT INTO account_deletion_file(job_operation_key,storage_key)
      VALUES ('f7c88768-32b7-44eb-a577-43e382fc2358','role-probe.webm');
      UPDATE account_deletion_job SET last_error_code=NULL
      WHERE operation_key='f7c88768-32b7-44eb-a577-43e382fc2358';
      DELETE FROM account_deletion_file WHERE storage_key='role-probe.webm';
      ROLLBACK;
    """,
        "aulas_runtime",
    )
    roles.sql(
        info,
        "SELECT id FROM transcription_job; UPDATE transcription_job SET status=status; "
        "SELECT id FROM assist_reservation; UPDATE assist_reservation SET state=state; "
        "SELECT operation_key FROM account_deletion_job; "
        "UPDATE account_deletion_job SET state=state; "
        "SELECT id FROM account_deletion_file; "
        "UPDATE account_deletion_file SET attempt_count=attempt_count; "
        "DELETE FROM account_deletion_file WHERE false;",
        "aulas_worker",
    )
    # Migrador realmente usa SET ROLE pelo driver e passa a guarda da conexão.
    roles.lab_run("migrator", "alembic", "upgrade", "head")
    roles.lab_run("migrator", "python", "/tools/roles_archive_smoke.py")
    roles.lab_run("migrator", "python", "/tools/roles_reorder_smoke.py")
    roles.lab_run("runtime", "python", "/tools/roles_app_smoke.py")
    roles.lab_run("runtime", "python", "/tools/roles_assist_smoke.py")
    roles.lab_run("worker", "python", "/tools/roles_assist_smoke.py")
    roles.lab_run("runtime", "python", "/tools/roles_dialogue_smoke.py")
    roles.lab_run("worker", "python", "/tools/roles_dialogue_smoke.py")
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
        "Papéis aprovados: recusas de privilégio, DML runtime, API HTTP e snapshots, "
        "cotas/retenção runtime/worker e dump limitado."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Ensaio de papéis falhou; não liberar rollout.", file=sys.stderr)
        raise SystemExit(1) from None
