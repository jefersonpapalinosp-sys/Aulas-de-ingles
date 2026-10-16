"""Backup conjunto e restore exclusivamente no laboratório vazio. Sem shell/segredos em logs."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ops.recovery_archive import (
    RecoveryError,
    audio_inventory,
    create_bundle,
    file_info,
    require,
    verify_bundle,
    write_json,
)

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = ROOT / "backups" / "recovery"
PROJECT = "aulas-ingles-recovery"
UPGRADE_PROJECT = "aulas-ingles-upgrade42"
HELPER = "aulas-ingles-recovery-tools:local"
POSTGRES = "public.ecr.aws/docker/library/postgres:16.15-alpine"
UPGRADE_FROM = "e41f6c2a8d90"
CONFIRM_TARGET = "aulas-ingles-recovery/target-db"
CONFIRM_STUDY_CHECK = "aulas-ingles-recovery/study-check-db"
CONFIRM_CONCURRENCY_CHECK = "aulas-ingles-recovery/concurrency-check-db"
CONFIRM_DEV_CHECK = "aulas-ingles-recovery/dev-check-db"
CONFIRM_ASSIST_CHECK = "aulas-ingles-recovery/assist-check-db"
CONFIRM_DEV39_CHECK = "aulas-ingles-recovery/dev39-check-db"
CONFIRM_STUDY39_CHECK = "aulas-ingles-recovery/study39-check-db"
CONFIRM_UPGRADE42 = "aulas-ingles-upgrade42/target-db"


@dataclass(frozen=True)
class Target:
    project: str
    service: str
    database: str
    role: str
    db_volume: str
    voice_volume: str
    marker: str | None


LAB = Target(
    PROJECT,
    "source-db",
    "aulas_ingles_test",
    "aulas_test",
    f"{PROJECT}_source_db",
    f"{PROJECT}_source_voice",
    "aulas-ingles:disposable-test:v1",
)
RESTORE = Target(
    PROJECT,
    "target-db",
    "aulas_ingles_restore",
    "aulas_restore",
    f"{PROJECT}_target_db",
    f"{PROJECT}_target_voice",
    "aulas-ingles:recovery-target:v1",
)
UPGRADE_LAB = Target(
    UPGRADE_PROJECT,
    "source-db",
    "aulas_ingles_test",
    "aulas_test",
    f"{UPGRADE_PROJECT}_source_db",
    f"{UPGRADE_PROJECT}_source_voice",
    "aulas-ingles:disposable-test:v1",
)
UPGRADE_RESTORE = Target(
    UPGRADE_PROJECT,
    "target-db",
    "aulas_ingles_restore",
    "aulas_restore",
    f"{UPGRADE_PROJECT}_target_db",
    f"{UPGRADE_PROJECT}_target_voice",
    "aulas-ingles:recovery-target:v1",
)


STUDY_CHECK = Target(
    PROJECT,
    "study-check-db",
    "aulas_ingles_restore",
    "aulas_restore",
    f"{PROJECT}_study_check_db",
    f"{PROJECT}_study_check_voice",
    "aulas-ingles:recovery-target:v1",
)
CONCURRENCY_CHECK = Target(
    PROJECT,
    "concurrency-check-db",
    "aulas_ingles_restore",
    "aulas_restore",
    f"{PROJECT}_concurrency_check_db",
    f"{PROJECT}_concurrency_check_voice",
    "aulas-ingles:recovery-target:v1",
)
DEV_CHECK = Target(
    PROJECT,
    "dev-check-db",
    "aulas_ingles_restore",
    "aulas_restore",
    f"{PROJECT}_dev_check_db",
    f"{PROJECT}_dev_check_voice",
    "aulas-ingles:recovery-target:v1",
)
ASSIST_CHECK = Target(
    PROJECT,
    "assist-check-db",
    "aulas_ingles_restore",
    "aulas_restore",
    f"{PROJECT}_assist_check_db",
    f"{PROJECT}_assist_check_voice",
    "aulas-ingles:recovery-target:v1",
)
DEV39_CHECK = Target(
    PROJECT,
    "dev39-check-db",
    "aulas_ingles_restore",
    "aulas_restore",
    f"{PROJECT}_dev39_check_db",
    f"{PROJECT}_dev39_check_voice",
    "aulas-ingles:recovery-target:v1",
)
STUDY39_CHECK = Target(
    PROJECT,
    "study39-check-db",
    "aulas_ingles_restore",
    "aulas_restore",
    f"{PROJECT}_study39_check_db",
    f"{PROJECT}_study39_check_voice",
    "aulas-ingles:recovery-target:v1",
)
DESTINATIONS = {
    CONFIRM_TARGET: RESTORE,
    CONFIRM_STUDY_CHECK: STUDY_CHECK,
    CONFIRM_CONCURRENCY_CHECK: CONCURRENCY_CHECK,
    CONFIRM_DEV_CHECK: DEV_CHECK,
    CONFIRM_ASSIST_CHECK: ASSIST_CHECK,
    CONFIRM_DEV39_CHECK: DEV39_CHECK,
    CONFIRM_STUDY39_CHECK: STUDY39_CHECK,
}
UPGRADE_DESTINATIONS = {CONFIRM_UPGRADE42: UPGRADE_RESTORE}


def run(args, *, stdin=None, stdout=None, timeout=120, reject_stderr=False):
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            stdin=stdin,
            stdout=stdout or subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=True,
        )
        require(
            not reject_stderr or not result.stderr,
            "Ferramenta de backup emitiu avisos; pacote não foi aprovado.",
        )
        return result.stdout or b""
    except (OSError, subprocess.SubprocessError) as exc:
        # Não incluir args/stderr: o ambiente errado poderia devolver dados privados.
        raise RecoveryError(
            "Comando operacional falhou; nenhum sucesso foi confirmado."
        ) from exc


def docker(*args, **kwargs):
    return run(["docker", *args], **kwargs)


def local_daemon():
    if os.environ.get("DOCKER_HOST"):
        require(
            os.environ["DOCKER_HOST"].startswith("unix:///"), "Docker remoto recusado."
        )
    endpoint = (
        docker("context", "inspect", "--format", "{{.Endpoints.docker.Host}}")
        .decode()
        .strip()
    )
    require(
        endpoint.startswith("unix:///"),
        "Exige Docker local via socket Unix (macOS/Linux).",
    )


def validate_volume(value, project, name, disposable):
    require(
        value["Name"] == name
        and value["Driver"] == "local"
        and value["Scope"] == "local"
        and not value.get("Options"),
        "Volume incorreto ou redirecionado.",
    )
    labels = value.get("Labels") or {}
    require(
        labels.get("com.docker.compose.project") == project, "Volume de outro projeto."
    )
    if disposable:
        require(
            labels.get("org.aulas.environment") == "disposable-recovery",
            "Volume sem marcador de recuperação descartável.",
        )


def volume(name, project, disposable=True):
    value = json.loads(docker("volume", "inspect", name))[0]
    validate_volume(value, project, name, disposable)


def lab_resources():
    local_daemon()
    existing = set(
        docker("volume", "ls", "--format", "{{.Name}}").decode().splitlines()
    )
    for name in (
        LAB.db_volume,
        LAB.voice_volume,
        RESTORE.db_volume,
        RESTORE.voice_volume,
        STUDY_CHECK.db_volume,
        STUDY_CHECK.voice_volume,
        CONCURRENCY_CHECK.db_volume,
        CONCURRENCY_CHECK.voice_volume,
        DEV_CHECK.db_volume,
        DEV_CHECK.voice_volume,
        ASSIST_CHECK.db_volume,
        ASSIST_CHECK.voice_volume,
        DEV39_CHECK.db_volume,
        DEV39_CHECK.voice_volume,
        STUDY39_CHECK.db_volume,
        STUDY39_CHECK.voice_volume,
    ):
        if name in existing:
            volume(name, PROJECT)


def upgrade_lab_resources():
    local_daemon()
    existing = set(
        docker("volume", "ls", "--format", "{{.Name}}").decode().splitlines()
    )
    for name in (
        UPGRADE_LAB.db_volume,
        UPGRADE_LAB.voice_volume,
        UPGRADE_RESTORE.db_volume,
        UPGRADE_RESTORE.voice_volume,
    ):
        if name in existing:
            volume(name, UPGRADE_PROJECT)


def container(project, service):
    ids = (
        docker(
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            f"label=com.docker.compose.service={service}",
        )
        .decode()
        .splitlines()
    )
    require(len(ids) == 1, "Container ausente ou ambíguo; alvo não confirmado.")
    value = json.loads(docker("inspect", ids[0]))[0]
    labels = value["Config"].get("Labels") or {}
    require(
        labels.get("com.docker.compose.project") == project
        and labels.get("com.docker.compose.service") == service,
        "Container de outro projeto.",
    )
    return value


def env_of(info):
    return dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)


def source_target(source):
    require(source in {"lab", "upgrade-lab", "dev", "prod"}, "Origem não permitida.")
    if source == "lab":
        return LAB
    if source == "upgrade-lab":
        return UPGRADE_LAB
    project = "aulas-ingles" if source == "dev" else "aulas-ingles-prod"
    env = env_of(container(project, "db"))
    database, role = env.get("POSTGRES_DB", ""), env.get("POSTGRES_USER", "")
    api_env = env_of(container(project, "api"))
    if source == "dev":
        require(api_env.get("APP_ENV") == "dev", "Origem não é desenvolvimento.")
        require(
            not api_env.get("DATABASE_PURPOSE"),
            "Desenvolvimento com papéis exige novo ensaio.",
        )
    if api_env.get("DATABASE_PURPOSE") == "runtime":
        role = "aulas_backup"
    require(
        bool(database)
        and bool(role)
        and database not in {"postgres", "template0", "template1"},
        "Banco/usuário da origem não identificados.",
    )
    return Target(
        project,
        "db",
        database,
        role,
        "aulas-ingles-pgdata" + ("-prod" if source == "prod" else ""),
        "aulas-ingles-speaking-data" + ("-prod" if source == "prod" else ""),
        None,
    )


def db_args(target, command):
    info = container(target.project, target.service)
    return [
        "exec",
        "-i",
        info["Id"],
        command,
        "-h",
        "/var/run/postgresql",
        "-p",
        "5432",
        "-U",
        target.role,
        "-d",
        target.database,
    ]


def query(target, sql):
    raw = docker(*db_args(target, "psql"), "-XAt", "-v", "ON_ERROR_STOP=1", "-c", sql)
    return json.loads(raw)


def expected_bind_source(actual, expected):
    # Docker Desktop pode expor o caminho da VM; não aceitar prefixos arbitrários.
    allowed = {str(expected)}
    if sys.platform == "darwin":
        allowed.add(f"/host_mnt{expected}")
    return actual in allowed


def check_target(target):
    local_daemon()
    info = container(target.project, target.service)
    require(info["State"]["Running"], "Banco não está ativo.")
    require(not info["HostConfig"]["Privileged"], "Banco privilegiado recusado.")
    volumes = [m for m in info["Mounts"] if m["Type"] == "volume"]
    require(
        len(volumes) == 1
        and volumes[0]["Name"] == target.db_volume
        and volumes[0]["Destination"] == "/var/lib/postgresql/data",
        "Mount de banco inesperado.",
    )
    require(
        info["Config"]["Image"] == POSTGRES, "Imagem PostgreSQL fora do contrato 16.15."
    )
    require(
        set(info["NetworkSettings"]["Networks"]) == {f"{target.project}_default"},
        "Banco conectado a rede inesperada.",
    )
    if target.project in {PROJECT, UPGRADE_PROJECT}:
        require(
            not info["HostConfig"].get("PortBindings"),
            "Laboratório não pode publicar portas.",
        )
        require(len(info["Mounts"]) == 2, "Mount adicional no laboratório.")
        init = next((m for m in info["Mounts"] if m["Type"] == "bind"), {})
        filename = (
            "test-db-init.sql"
            if target in {LAB, UPGRADE_LAB}
            else "restore-db-init.sql"
        )
        require(
            expected_bind_source(init.get("Source"), ROOT / "infra" / filename)
            and init.get("Destination") == "/docker-entrypoint-initdb.d/01-test.sql"
            and not init.get("RW"),
            "Init SQL inesperado ou gravável.",
        )
    else:
        require(len(info["Mounts"]) == 1, "Mount adicional no banco de origem.")
        if target.project == "aulas-ingles":
            require(
                info["HostConfig"].get("PortBindings")
                == {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5433"}]},
                "Banco de desenvolvimento deve estar somente em 127.0.0.1:5433.",
            )
    for name in (target.db_volume, target.voice_volume):
        volume(name, target.project, target.project == PROJECT)
    identity = query(
        target,
        """
        SELECT json_build_object('database',current_database(),'role',current_user,
          'marker',shobj_description(d.oid,'pg_database'),'super',r.rolsuper,
          'createdb',r.rolcreatedb,'createrole',r.rolcreaterole,'bypassrls',r.rolbypassrls,
          'replication',r.rolreplication,'version',current_setting('server_version_num')::int)
        FROM pg_database d JOIN pg_roles r ON r.rolname=current_user
        WHERE d.datname=current_database()
    """,
    )
    require(
        identity["database"] == target.database
        and identity["role"] == target.role
        and 160000 <= identity["version"] < 170000,
        "Identidade/versão de banco divergente.",
    )
    if target.marker:
        require(
            identity["marker"] == target.marker
            and not any(
                identity[k]
                for k in ("super", "createdb", "createrole", "bypassrls", "replication")
            ),
            "Marcador/papel limitado não confirmado.",
        )
    if target.role == "aulas_backup":
        require(
            not any(
                identity[k]
                for k in ("super", "createdb", "createrole", "bypassrls", "replication")
            ),
            "Backup não pode usar privilégio global.",
        )
    return info


def quiet(target):
    # Não para containers nem encerra sessões; o operador deve abrir janela de manutenção.
    if target.project in {"aulas-ingles", "aulas-ingles-prod"}:
        for service in ("api", "worker"):
            info = container(target.project, service)
            require(
                not info["State"]["Running"],
                "Backup exige API e worker parados em manutenção autorizada.",
            )
            env = env_of(info)
            url = urlsplit(env.get("DATABASE_URL", ""))
            require(
                url.hostname == "db" and url.path == f"/{target.database}",
                "Aplicação aponta para banco diferente da origem.",
            )
            require(
                set(info["NetworkSettings"]["Networks"])
                == {f"{target.project}_default"},
                "Aplicação conectada a rede inesperada.",
            )
            require(
                env.get("SPEAKING_STORAGE_DIR") == "/app/data/speaking"
                and any(
                    m.get("Name") == target.voice_volume
                    and m["Destination"] == "/app/data/speaking"
                    for m in info["Mounts"]
                ),
                "Storage da aplicação divergente.",
            )
    require(
        not docker("ps", "-q", "--filter", f"volume={target.voice_volume}").strip(),
        "Há container ativo com acesso ao volume de voz. Backup/restore recusado.",
    )
    clients = query(
        target,
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE datname=current_database() AND pid<>pg_backend_pid()",
    )
    require(clients == 0, "Há outras conexões no banco; quiescência não confirmada.")


SNAPSHOT_SQL = """
SELECT json_build_object(
 'revision',(SELECT json_agg(version_num ORDER BY version_num) FROM public.alembic_version),
 'counts',json_build_object('users',(SELECT count(*) FROM public.app_user),
   'lessons',(SELECT count(*) FROM public.lesson),
   'speaking',(SELECT count(*) FROM public.speaking_attempt),
   'writing_feedback',(SELECT count(*) FROM public.writing_feedback),
   'writing_drafts',(SELECT count(*) FROM public.writing_draft),
   'writing_revisions',(SELECT count(*) FROM public.writing_revision),
   'attempts',(SELECT count(*) FROM public.exercise_attempt),
   'practice_sessions',(SELECT count(*) FROM public.practice_session),
   'practice_items',(SELECT count(*) FROM public.practice_session_item),
   'review_items',(SELECT count(*) FROM public.review_item),
   'study_sessions',(SELECT count(*) FROM public.study_session_progress),
   'step_progress',(SELECT count(*) FROM public.step_progress),
   'activity_sessions',(SELECT count(*) FROM public.study_activity_session),
   'activity_events',(SELECT count(*) FROM public.study_activity_event),
   'active_intervals',(SELECT count(*) FROM public.study_active_interval),
   'media_progress',(SELECT count(*) FROM public.media_progress),
   'lesson_progress',(SELECT count(*) FROM public.lesson_progress),
   'notebook_entries',(SELECT count(*) FROM public.notebook_entry),
   'transcription_jobs',(SELECT count(*) FROM public.transcription_job)),
 'audio',(SELECT coalesce(json_agg(json_build_object(
   'id',id,'key',storage_key,'size',file_size,'status',status)
   ORDER BY id),'[]'::json) FROM public.speaking_attempt))
"""


def voice(target, action, *, stdin=None, stdout=None):
    require(action in {"export", "import"}, "Ação de voz inválida.")
    require(
        action != "import"
        or target in DESTINATIONS.values()
        or target in UPGRADE_DESTINATIONS.values(),
        "Escrita de voz só no destino descartável.",
    )
    args = [
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "--mount",
        f"type=bind,src={ROOT / 'ops'},dst=/tools,readonly",
    ]
    if action == "export":
        args += [
            "--user",
            "10001:10001",
            "--mount",
            f"type=volume,src={target.voice_volume},dst=/voice,readonly",
        ]
    else:
        args += [
            "--user",
            "0:0",
            "--cap-add",
            "CHOWN",
            "--cap-add",
            "DAC_OVERRIDE",
            "--cap-add",
            "FOWNER",
            "--mount",
            f"type=volume,src={target.voice_volume},dst=/voice",
        ]
    docker(
        *args,
        "--entrypoint",
        "python",
        HELPER,
        "/tools/voice_transfer.py",
        action,
        stdin=stdin,
        stdout=stdout,
        timeout=600,
    )


@contextmanager
def lease(name):
    # Nome global no daemon impede duas cópias do repo restaurarem o mesmo alvo juntas.
    lock = (
        docker(
            "create",
            "--name",
            f"aulas-recovery-{name}-lock",
            "--network",
            "none",
            "--label",
            "org.aulas.purpose=recovery-lock",
            "--entrypoint",
            "true",
            HELPER,
        )
        .decode()
        .strip()
    )
    try:
        yield
    finally:
        docker("rm", lock)


def application_info(target):
    deployed = []
    if target.project in {"aulas-ingles", "aulas-ingles-prod"}:
        for service in ("api", "worker"):
            info = container(target.project, service)
            deployed.append(
                {
                    "service": service,
                    "image_id": info["Image"],
                    "image_ref": info["Config"]["Image"],
                }
            )
    return {
        "deployed_containers": deployed,
        "tools_image_id": json.loads(docker("image", "inspect", HELPER))[0]["Id"],
        "worktree_head": run(["git", "rev-parse", "HEAD"]).decode().strip(),
        "worktree_dirty": bool(run(["git", "status", "--porcelain"])),
        "note": "Worktree não representa necessariamente a versão implantada; "
        "use os IDs de imagem e schema.",
    }


def backup(source):
    local_daemon()
    target = source_target(source)
    info = check_target(target)
    quiet(target)
    with lease(f"backup-{source}"):

        def capture(staging):
            quiet(target)
            snapshot = query(target, SNAPSHOT_SQL)
            with (staging / "database.dump").open("xb") as stream:
                docker(
                    *db_args(target, "pg_dump"),
                    "-Fc",
                    stdout=stream,
                    timeout=600,
                    reject_stderr=True,
                )
            with (staging / "database.dump").open("rb") as stream:
                # --list valida o índice, não todos os blocos; só o restore ensaia a carga.
                docker("exec", "-i", info["Id"], "pg_restore", "--list", stdin=stream)
            with (staging / "voice.tar").open("xb") as stream:
                voice(target, "export", stdout=stream)
            quiet(target)
            require(
                query(target, SNAPSHOT_SQL) == snapshot,
                "Banco mudou durante captura; pacote não publicado.",
            )
            return {
                "snapshot": snapshot,
                "source": {
                    "kind": source,
                    "project": target.project,
                    "database": target.database,
                    "db_container_id": info["Id"],
                    "db_image_id": info["Image"],
                    "voice_volume": target.voice_volume,
                    "consistency": "maintenance-quiescent",
                },
                "application": application_info(target),
            }

        return create_bundle(BACKUPS, capture)


EMPTY_SQL = """
SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema')
     + (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema')
     + (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema')
     + (SELECT count(*) FROM pg_namespace WHERE nspname !~ '^pg_'
        AND nspname NOT IN ('public','information_schema'))
"""


def restore(path, confirm):
    require(
        confirm in DESTINATIONS or confirm in UPGRADE_DESTINATIONS,
        "Confirme explicitamente um destino isolado permitido.",
    )
    destination = (DESTINATIONS | UPGRADE_DESTINATIONS)[confirm]
    manifest = verify_bundle(path)  # Antes de qualquer comando Docker ou mutação.
    check_target(destination)
    started = time.monotonic()
    with lease("restore"):
        quiet(destination)
        require(
            query(destination, EMPTY_SQL) == 0,
            "Destino PostgreSQL não está vazio; nada foi removido.",
        )
        with tempfile.TemporaryDirectory(prefix="aulas-restore-check-") as temporary:
            current_voice = Path(temporary) / "voice.tar"
            with current_voice.open("xb") as stream:
                voice(destination, "export", stdout=stream)
            require(
                not audio_inventory(current_voice),
                "Destino de voz não está vazio; nada foi removido.",
            )
        with (Path(path) / "database.dump").open("rb") as stream:
            docker(
                *db_args(destination, "pg_restore"),
                "--single-transaction",
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                stdin=stream,
                timeout=600,
            )
        with (Path(path) / "voice.tar").open("rb") as stream:
            voice(destination, "import", stdin=stream)
        # Só o par validado abaixo é aprovado. Falha preserva o destino parcial.
        require(
            query(destination, SNAPSHOT_SQL) == manifest["snapshot"],
            "Snapshot restaurado diverge da origem.",
        )
        with tempfile.TemporaryDirectory(prefix="aulas-restored-voice-") as temporary:
            restored_voice = Path(temporary) / "voice.tar"
            with restored_voice.open("xb") as stream:
                voice(destination, "export", stdout=stream)
            require(
                audio_inventory(restored_voice) == manifest["audio_files"],
                "Áudios restaurados divergem.",
            )
        quiet(destination)
        # Não modificar o pacote publicado: recibo separado, também privado.
        receipts = BACKUPS / "restore-receipts"
        require(
            not BACKUPS.is_symlink() and not receipts.is_symlink(),
            "Diretório de recibos não pode ser link.",
        )
        receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(
            receipts.stat().st_mode & 0o077 == 0,
            "Diretório de recibos deve ser privado.",
        )
        receipt = receipts / f"{manifest['bundle_id']}.json"
        write_json(
            receipt,
            {
                "bundle_id": manifest["bundle_id"],
                "target": confirm,
                "manifest": file_info(Path(path) / "manifest.json"),
                "audio_count": len(manifest["audio_files"]),
                "seconds": round(time.monotonic() - started, 3),
                "verified": True,
            },
        )
        return receipt


def lab_prepare():
    check_target(LAB)
    with lease("backup-lab"):
        _prepare_empty_lab()


def _prepare_empty_lab():
    quiet(LAB)
    require(
        query(LAB, EMPTY_SQL) == 0,
        "Origem de ensaio já preparada; não sobrescrever dados.",
    )
    args = [
        "run",
        "--rm",
        "--network",
        f"{PROJECT}_default",
        "-e",
        "APP_ENV=test",
        "-e",
        "DATABASE_URL=postgresql+asyncpg://aulas_test:aulas_test_only@source-db:5432/aulas_ingles_test",
        "-e",
        "SPEAKING_STORAGE_DIR=/app/data/speaking",
        "--mount",
        f"type=volume,src={LAB.voice_volume},dst=/app/data/speaking",
        "--mount",
        f"type=bind,src={ROOT / 'ops'},dst=/tools,readonly",
        HELPER,
    ]
    docker(*args, "python", "-m", "app.testing", "prepare", timeout=180)
    docker(*args, "python", "/tools/recovery_fixture.py", timeout=60)


def upgrade_lab_prepare():
    check_target(UPGRADE_LAB)
    with lease("upgrade42-source"):
        quiet(UPGRADE_LAB)
        args = [
            "run",
            "--rm",
            "--network",
            f"{UPGRADE_PROJECT}_default",
            "-e",
            "APP_ENV=test",
            "-e",
            "DATABASE_URL=postgresql+asyncpg://aulas_test:aulas_test_only@source-db:5432/aulas_ingles_test",
            "-e",
            "SPEAKING_STORAGE_DIR=/app/data/speaking",
            "--mount",
            f"type=volume,src={UPGRADE_LAB.voice_volume},dst=/app/data/speaking",
            "--mount",
            f"type=bind,src={ROOT / 'ops'},dst=/tools,readonly",
            HELPER,
        ]
        # Nasce diretamente na revisão anterior: nenhum downgrade ou dado
        # removido é usado para fabricar o ensaio. Uma execução interrompida
        # pode ser retomada apenas no estado intermediário exato e sem dados
        # pessoais/editoriais; qualquer outro estado é preservado e recusado.
        docker(*args, "python", "-m", "app.testing", "check", timeout=60)
        if query(UPGRADE_LAB, EMPTY_SQL) == 0:
            docker(*args, "alembic", "upgrade", UPGRADE_FROM, timeout=180)
        else:
            state = query(
                UPGRADE_LAB,
                "SELECT json_build_object("
                "'revision',(SELECT json_agg(version_num ORDER BY version_num) "
                "FROM public.alembic_version),"
                "'users',(SELECT count(*) FROM public.app_user),"
                "'lessons',(SELECT count(*) FROM public.lesson))",
            )
            require(
                state == {"revision": [UPGRADE_FROM], "users": 0, "lessons": 0},
                "Origem de upgrade não está no ponto intermediário retomável.",
            )
        with tempfile.TemporaryDirectory(prefix="aulas-upgrade42-source-") as temporary:
            current_voice = Path(temporary) / "voice.tar"
            with current_voice.open("xb") as stream:
                voice(UPGRADE_LAB, "export", stdout=stream)
            require(
                not audio_inventory(current_voice),
                "Origem de voz já contém dados; preparação recusada.",
            )
        docker(*args, "python", "/tools/recovery_fixture.py", timeout=60)


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("backup")
    capture.add_argument(
        "--source", choices=("lab", "upgrade-lab", "dev", "prod"), required=True
    )
    verify = commands.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    load = commands.add_parser("restore")
    load.add_argument("bundle", type=Path)
    load.add_argument(
        "--confirm",
        required=True,
        choices=tuple(DESTINATIONS | UPGRADE_DESTINATIONS),
    )
    commands.add_parser("lab-resources")
    commands.add_parser("lab-prepare")
    commands.add_parser("upgrade-lab-resources")
    commands.add_parser("upgrade-lab-prepare")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            print(
                "Pacote publicado (integridade verificada; restore é etapa separada): "
                f"{backup(args.source)}"
            )
        elif args.command == "verify":
            verify_bundle(args.bundle)
            print(
                "Integridade do pacote e referências de voz verificadas; isto não executa restore."
            )
        elif args.command == "restore":
            print(
                f"Restore isolado verificado. Recibo: {restore(args.bundle, args.confirm)}"
            )
        elif args.command == "lab-resources":
            lab_resources()
            print("Recursos locais de recuperação verificados.")
        elif args.command == "lab-prepare":
            lab_prepare()
            print("Origem sintética preparada; nenhum ambiente de estudo foi alterado.")
        elif args.command == "upgrade-lab-resources":
            upgrade_lab_resources()
            print("Recursos isolados do ensaio de upgrade verificados.")
        elif args.command == "upgrade-lab-prepare":
            upgrade_lab_prepare()
            print("Origem sintética criada diretamente na revisão anterior.")
    except RecoveryError as exc:
        print(
            f"Operação recusada: {exc} Parciais são preservados; não use restore legado.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "Operação falhou; nenhum sucesso foi confirmado. "
            "Preserve pacote/destino parcial para diagnóstico.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
