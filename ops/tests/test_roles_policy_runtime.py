"""Ensaio opt-in de grants com cluster UUID, sem portas ou volumes persistentes."""

import json
import os
import subprocess
import time
import unittest
from uuid import uuid4

from ops import recovery, roles
from ops.recovery_archive import RecoveryError
from ops.roles_verify import verify_policy

IMAGE = os.environ.get("AULAS_ROLES_TEST_IMAGE", "")


def docker(*args, data=None):
    result = subprocess.run(
        ["docker", *args], input=data, capture_output=True, timeout=180, check=False
    )
    if result.returncode:
        error = subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
        error.add_note(result.stderr.decode(errors="replace")[-3000:])
        raise error
    return result.stdout


@unittest.skipUnless(IMAGE, "requer imagem explícita e Docker para cluster descartável")
class RolesPolicyRuntimeTests(unittest.TestCase):
    def test_effective_policy_detects_column_drift_and_reconciles(self):
        name = "aulas-dr-policy56-" + uuid4().hex[:12]
        db, app = name + "-db", name + "-migrate"
        docker("network", "create", "--internal", name)
        try:
            docker(
                "run",
                "-d",
                "--name",
                db,
                "--network",
                name,
                "--network-alias",
                "db",
                "--tmpfs",
                "/var/lib/postgresql/data",
                "--env",
                "POSTGRES_USER=lab_admin",
                "--env",
                "POSTGRES_PASSWORD=disposable-only",
                recovery.POSTGRES,
            )
            for _ in range(60):
                try:
                    docker("exec", db, "pg_isready", "-h", "127.0.0.1", "-U", "lab_admin")
                    break
                except subprocess.CalledProcessError:
                    time.sleep(1)
            sql = "CREATE ROLE aulas_owner NOLOGIN;\n"
            for role in ("migrator", "runtime", "worker", "backup"):
                sql += f"CREATE ROLE aulas_{role} LOGIN PASSWORD 'synthetic-lab-only';\n"
            sql += (
                "GRANT aulas_owner TO aulas_migrator;\n"
                "CREATE DATABASE aulas_roles_lab OWNER aulas_owner;\n"
            )
            docker(
                "exec",
                "-i",
                db,
                "psql",
                "-Xq",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "lab_admin",
                "-d",
                "postgres",
                data=sql.encode(),
            )
            docker(
                "create",
                "--name",
                app,
                "--network",
                name,
                "--env",
                "APP_ENV=dev",
                "--env",
                "DATABASE_PURPOSE=migrator",
                "--env",
                "DATABASE_URL=postgresql+asyncpg://aulas_migrator:synthetic-lab-only@db:5432/aulas_roles_lab",
                "--entrypoint",
                "sh",
                IMAGE,
                "-ec",
                "alembic upgrade head && alembic check && python -m app.cli seed",
            )
            for source, destination in (
                ("backend/app", "/app/app"),
                ("backend/alembic", "/app/alembic"),
                ("backend/alembic.ini", "/app/alembic.ini"),
                ("seed", "/app/seed"),
            ):
                # docker cp transmite bytes; não depende de binds do host do daemon.
                path = recovery.ROOT / source
                docker("cp", str(path) + ("/." if path.is_dir() else ""), f"{app}:{destination}")
            docker("start", "-a", app)
            info = json.loads(docker("inspect", db))[0]
            target = (info, "aulas_roles_lab", "lab_admin")
            self.assertEqual(
                roles.sql(target, "SELECT version_num FROM alembic_version").strip(),
                b"f61a1b8c9009",
            )
            policy = (recovery.ROOT / "ops/roles_policy.sql").read_text()
            roles.sql(target, "BEGIN;\n" + policy + "\nCOMMIT;")
            verify_policy(target)
            self.assertEqual(
                roles.sql(target, "SELECT "
                    "has_table_privilege('aulas_runtime','listening_resource','SELECT'), "
                    "has_table_privilege('aulas_runtime','listening_resource','UPDATE'), "
                    "has_table_privilege('aulas_runtime','listening_progress','UPDATE'), "
                    "has_table_privilege('aulas_runtime','listening_operation','INSERT'), "
                    "has_table_privilege('aulas_runtime','listening_operation','UPDATE'), "
                    "has_table_privilege('aulas_worker','listening_progress','SELECT'), "
                    "has_table_privilege('aulas_backup','listening_operation','SELECT')").strip(),
                b"t|f|t|t|f|f|t",
            )
            self.assertEqual(roles.sql(target, "SELECT "
                "has_table_privilege('aulas_runtime','native_listening_version','SELECT'), "
                "has_table_privilege('aulas_runtime','native_listening_version','UPDATE'), "
                "has_table_privilege('aulas_runtime','native_listening_session','INSERT'), "
                "has_table_privilege('aulas_runtime','native_listening_session','UPDATE'), "
                "has_table_privilege('aulas_runtime','native_listening_response','INSERT'), "
                "has_table_privilege('aulas_runtime','native_listening_response','UPDATE'), "
                "has_table_privilege('aulas_worker','native_listening_session','SELECT'), "
                "has_table_privilege('aulas_backup','native_listening_response','SELECT')"
            ).strip(), b"t|f|t|t|t|f|f|t")
            self.assertEqual(roles.sql(target, "SELECT "
                "has_table_privilege('aulas_runtime','native_listening_position','INSERT'), "
                "has_table_privilege('aulas_runtime','native_listening_position','UPDATE'), "
                "has_table_privilege('aulas_worker','native_listening_position','SELECT'), "
                "has_table_privilege('aulas_backup','native_listening_position','SELECT')"
            ).strip(), b"t|t|f|t")
            self.native_restore(target, db)
            roles.sql(target, "GRANT UPDATE (title) ON lesson TO aulas_runtime;")
            with self.assertRaises(RecoveryError):
                verify_policy(target)
            with self.assertRaises(RecoveryError):
                roles.sql(target, "BEGIN;\n" + policy + "\nSELECT missing_s56_function();\nCOMMIT;")
            # A comparação reverte sua aplicação temporária: a divergência continua visível.
            self.assertEqual(
                roles.sql(
                    target, "SELECT has_column_privilege('aulas_runtime','lesson','title','UPDATE')"
                ).strip(),
                b"t",
            )
            roles.sql(target, "BEGIN;\n" + policy + "\nCOMMIT;")
            verify_policy(target)
            self.assertEqual(
                roles.sql(
                    target, "SELECT has_column_privilege('aulas_runtime','lesson','title','UPDATE')"
                ).strip(),
                b"f",
            )
            print(
                json.dumps(
                    {
                        "lab": name,
                        "effective_grants": "matched",
                        "column_drift": "detected-and-revoked",
                    }
                )
            )
        finally:
            for container in (app, db):
                subprocess.run(["docker", "rm", "-f", container], capture_output=True, check=False)
            docker("network", "rm", name)

    def native_restore(self, target, db):
        """Dados sintéticos no dump completo; áudio recuperado da imagem versionada."""
        roles.sql(target, """BEGIN; SET LOCAL ROLE aulas_runtime;
          INSERT INTO app_user(id,email,password_hash,display_name)
            VALUES(90000001,'restore60@example.invalid','synthetic-not-a-password','Restore 60');
          INSERT INTO native_listening_session(id,user_id,version_id,operation_key,revision)
            SELECT 90000001,90000001,id,'00000000-0000-4000-8000-000000000060',1
              FROM native_listening_version WHERE slug='hotel-riverside' AND version=1;
          INSERT INTO native_listening_response
            (user_id,session_id,operation_key,expected_revision,revision,payload)
            VALUES(90000001,90000001,'00000000-0000-4000-8000-000000000061',0,1,
              '{"kind":"answer","question_id":"stay","selected_ids":["two"]}');
          INSERT INTO native_listening_position
            (user_id,session_id,position_seconds,revision,completed)
            VALUES(90000001,90000001,18,1,false);
          COMMIT;""")
        inventory = """SELECT json_build_object(
          'versions',(SELECT json_agg(t ORDER BY id) FROM native_listening_version t),
          'sessions',(SELECT json_agg(t ORDER BY id) FROM native_listening_session t),
          'responses',(SELECT json_agg(t ORDER BY id) FROM native_listening_response t),
          'positions',(SELECT json_agg(t ORDER BY id) FROM native_listening_position t))"""
        before = roles.sql(target, inventory)
        archive = docker(
            "exec", db, "pg_dump", "-U", "aulas_backup", "-d", "aulas_roles_lab", "-Fc"
        )
        docker("exec", db, "createdb", "-U", "lab_admin", "aulas_native_restore60")
        docker("exec", "-i", db, "pg_restore", "--exit-on-error", "--no-owner", "--no-privileges",
               "-U", "lab_admin", "-d", "aulas_native_restore60", data=archive)
        restored = (target[0], "aulas_native_restore60", "lab_admin")
        self.assertEqual(roles.sql(restored, inventory), before)
        # Arquivos didáticos são ativos da release, não gravações pessoais de speaking.
        script = """import hashlib,json,pathlib
root=pathlib.Path('/app/seed/listening-native')
items=json.loads((root/'activities.json').read_text())
assert len(items)==3
for item in items:
    path=root/'audio'/item['audio_file']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==item['audio_sha256']
print('native-assets-restored:3')
"""
        self.assertEqual(docker("run", "--rm", "--network", "none", "--entrypoint", "python",
                                IMAGE, "-c", script).strip(), b"native-assets-restored:3")
        # A cascata restaurada continua funcional, preservando as versões compartilhadas.
        roles.sql(restored, "DELETE FROM app_user WHERE id=90000001")
        self.assertEqual(roles.sql(restored, "SELECT "
            "(SELECT count(*) FROM native_listening_session),"
            "(SELECT count(*) FROM native_listening_response),"
            "(SELECT count(*) FROM native_listening_position),"
            "(SELECT count(*) FROM native_listening_version)").strip(), b"0|0|0|3")
