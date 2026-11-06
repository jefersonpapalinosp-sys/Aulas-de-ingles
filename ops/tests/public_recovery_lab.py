"""Ensaio opt-in no daemon local: recursos UUID, dados sintéticos e age real."""

import json
import os
import shlex
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from ops import public_backup, public_restore, recovery
from ops.recovery_archive import RecoveryError, require


def main():
    require(
        os.environ.get("AULAS_PUBLIC_RECOVERY_LAB") == "synthetic-only",
        "Ensaio exige opt-in explícito.",
    )
    recovery.local_daemon()
    controller = os.environ["HOSTNAME"]
    mounts = json.loads(recovery.docker("inspect", "--format", "{{json .Mounts}}", controller))
    host_tmp = next(m["Source"] for m in mounts if m["Destination"] == "/tmp")
    if len(host_tmp) > 2 and host_tmp[1:3] == ":\\":
        host_tmp = "/run/desktop/mnt/host/" + host_tmp[0].lower() + host_tmp[2:].replace("\\", "/")
    run_id = uuid4().hex[:12]
    source = f"aulas-dr-source-{run_id}"
    target = f"aulas-dr-target-{run_id}"
    image = "aulas-ingles-api:latest"
    containers = []
    volumes = []
    work = Path("/tmp") / f"recovery54-{run_id}"
    work.mkdir(mode=0o700)
    success = False
    started = time.monotonic()

    def create(*args):
        identity = recovery.docker("create", *args).decode().strip()
        containers.append(identity)
        return identity

    def sql(project, statement):
        with tempfile.TemporaryFile() as stream:
            stream.write(statement.encode())
            stream.seek(0)
            return recovery.docker(
                "exec",
                "-i",
                f"{project}-db-1",
                "psql",
                "-U",
                "aulas_admin",
                "-d",
                "aulas_ingles",
                "-XAt",
                "-v",
                "ON_ERROR_STOP=1",
                stdin=stream,
            )

    def prepare(project):
        for suffix in ("pgdata", "speaking_data"):
            name = f"{project}_{suffix}"
            recovery.docker(
                "volume", "create", "--label", f"com.docker.compose.project={project}", name
            )
            volumes.append((name, project))
        db = create(
            "--name",
            f"{project}-db-1",
            "--network",
            "none",
            "--label",
            f"com.docker.compose.project={project}",
            "--label",
            "com.docker.compose.service=db",
            "-e",
            "POSTGRES_USER=aulas_admin",
            "-e",
            "POSTGRES_DB=aulas_ingles",
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--mount",
            f"type=volume,src={project}_pgdata,dst=/var/lib/postgresql/data",
            recovery.POSTGRES,
        )
        recovery.docker("start", db)
        for _ in range(60):
            try:
                sql(project, "SELECT 1;")
                break
            except RecoveryError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Banco sintético não ficou pronto.")
        with tempfile.TemporaryFile() as script:
            # Executar via sh após converter somente a cópia sintética do script para LF.
            script.write(
                (recovery.ROOT / "infra/easypanel/postgres-init.sh")
                .read_bytes()
                .replace(b"\r\n", b"\n")
            )
            script.seek(0)
            recovery.docker(
                "exec",
                "-i",
                "-e",
                "AULAS_MIGRATOR_PASSWORD=synthetic",
                "-e",
                "AULAS_RUNTIME_PASSWORD=synthetic",
                "-e",
                "AULAS_WORKER_PASSWORD=synthetic",
                "-e",
                "AULAS_BACKUP_PASSWORD=synthetic",
                db,
                "sh",
                stdin=script,
            )
        sql(
            project,
            "COMMENT ON DATABASE aulas_ingles IS 'aulas-ingles:public-recovery54:synthetic';",
        )
        for service in ("api", "worker", "web"):
            args = [
                "--name",
                f"{project}-{service}-1",
                "--network",
                f"container:{db}",
                "--label",
                f"com.docker.compose.project={project}",
                "--label",
                f"com.docker.compose.service={service}",
            ]
            if service in {"api", "worker"}:
                args += [
                    "--mount",
                    f"type=volume,src={project}_speaking_data,dst=/app/data/speaking",
                ]
            create(*args, "--entrypoint", "sleep", image, "infinity")

    def app_task(project, command, name):
        recovery.docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--mount",
            f"type=volume,src={project}_speaking_data,dst=/voice",
            "--entrypoint",
            "chown",
            image,
            "10001:10001",
            "/voice",
        )
        task = create(
            "--name",
            f"{project}-{name}",
            "--user",
            "10001:10001",
            "--network",
            f"container:{project}-db-1",
            "-e",
            "APP_ENV=dev",
            "-e",
            "DATABASE_PURPOSE=migrator",
            "-e",
            "DATABASE_URL=postgresql+asyncpg://aulas_migrator:synthetic@127.0.0.1:5432/aulas_ingles",
            "-e",
            "PYTHONPATH=/app:/work",
            "--mount",
            f"type=volume,src={project}_speaking_data,dst=/app/data/speaking",
            "--entrypoint",
            "python",
            image,
            *command,
        )
        recovery.docker("cp", str(recovery.ROOT / "backend") + "/.", f"{task}:/app/")
        recovery.docker("cp", str(recovery.ROOT / "ops"), f"{task}:/app/ops")
        recovery.docker("start", "-a", task, timeout=180)
        code = json.loads(recovery.docker("inspect", "--format", "{{.State.ExitCode}}", task))
        require(code == 0, "Preparação sintética falhou.")

    transport = public_backup.transport

    def desktop_transport(host, command):
        # Só traduz o bind /tmp compartilhado: Docker Desktop não vê o /tmp do controller.
        if "src=/tmp/" in command:
            command = shlex.join(
                [part.replace("src=/tmp/", f"src={host_tmp}/") for part in shlex.split(command)]
            )
        return transport(host, command)

    try:
        prepare(source)
        prepare(target)
        app_task(source, ["-m", "alembic", "upgrade", "head"], "migrate")
        app_task(source, ["-m", "ops.tests.public_recovery_fixture"], "fixture")
        with (recovery.ROOT / "ops/roles_policy.sql").open("rb") as stream:
            recovery.docker(
                "exec",
                "-i",
                f"{source}-db-1",
                "psql",
                "-U",
                "aulas_admin",
                "-d",
                "aulas_ingles",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                stdin=stream,
            )
        with (
            patch.object(
                public_backup, "container", side_effect=lambda service: f"{source}-{service}-1"
            ),
            patch.object(public_backup, "voice_volume", return_value=f"{source}_speaking_data"),
            patch.object(public_backup, "api_image", return_value=image),
            patch.object(
                public_backup,
                "worktree_info",
                return_value={"worktree_head": "synthetic", "worktree_dirty": True},
            ),
            patch.object(public_backup, "transport", side_effect=desktop_transport),
            patch.object(recovery, "BACKUPS", work / "recovery"),
        ):
            # Comprovar MVCC: escrita de estudo posterior não entra no dump da captura.
            original_export = public_backup.exported_snapshot

            from contextlib import contextmanager

            @contextmanager
            def concurrent_snapshot(host):
                with original_export(host) as value:
                    sql(
                        source,
                        "INSERT INTO app_user(email,password_hash,display_name) "
                        "VALUES('later@example.invalid','!disabled!','Synthetic later');",
                    )
                    yield value

            with patch.object(public_backup, "exported_snapshot", concurrent_snapshot):
                bundle = public_backup.capture("local", attempts=1)
            identity = work / "synthetic-age-key"
            recovery.run(["age-keygen", "-o", str(identity)])
            recipient = recovery.run(["age-keygen", "-y", str(identity)]).decode().strip()
            encrypted = public_backup.encrypt(bundle, recipient, work / "encrypted")
            external = work / "external"
            external.mkdir(mode=0o700)
            copied = public_backup.copy_external(encrypted["path"], external)
            restore_start = time.monotonic()
            opened = public_restore.unseal(Path(copied["path"]), identity, work / "opened")
            receipt = public_restore.restore(
                opened,
                public_restore.Destination("local", target),
                f"local/{target}",
                work / "receipts",
            )
            # Backup capturou 1 conta; origem já tinha 2. Restore deve conter exatamente 1.
            require(
                sql(source, "SELECT count(*) FROM app_user;").strip() == b"2",
                "MVCC não exercitado.",
            )
            require(
                sql(target, "SELECT count(*) FROM app_user;").strip() == b"1", "Snapshot incorreto."
            )
            report = json.loads(receipt.read_text())
            report.update(
                {
                    "unseal_and_restore_seconds": round(time.monotonic() - restore_start, 3),
                    "lab_total_seconds": round(time.monotonic() - started, 3),
                    "real_age": True,
                    "concurrent_study_write": True,
                }
            )
            print(json.dumps(report, indent=2))
            success = True
    finally:
        for identity in reversed(containers):
            recovery.docker("rm", "-f", identity)
        if success:
            for name, project in volumes:
                labels = json.loads(
                    recovery.docker("volume", "inspect", "--format", "{{json .Labels}}", name)
                )
                require(
                    labels.get("com.docker.compose.project") == project,
                    "Volume mudou de identidade.",
                )
                recovery.docker("volume", "rm", name)


if __name__ == "__main__":
    main()
