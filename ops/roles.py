"""Provisionamento explícito, sem imprimir credenciais e sem revogar o administrador."""

import argparse
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from ops import recovery
from ops.recovery_archive import file_info, require, verify_bundle, write_json

PROJECT = "aulas-ingles-roles"
NAMES = ("aulas_owner", "aulas_migrator", "aulas_runtime", "aulas_worker", "aulas_backup")
MARKER = "aulas-ingles:role-v1"


def resources():
    recovery.local_daemon()
    names = recovery.docker("volume", "ls", "--format", "{{.Name}}").decode().splitlines()
    name = f"{PROJECT}_pgdata"
    if name in names:
        value = json.loads(recovery.docker("volume", "inspect", name))[0]
        recovery.validate_volume(value, PROJECT, name, False)
        require(
            (value.get("Labels") or {}).get("org.aulas.environment") == "disposable-roles",
            "Volume sem marcador de ensaio de papéis.",
        )


def target(scope):
    recovery.local_daemon()
    if scope == "prod":
        selected = recovery.source_target("prod")
        info = recovery.check_target(selected)
        recovery.quiet(selected)
        # O backup usa papel de leitura após rollout; provisionamento continua
        # administrativo, sempre sob manutenção e nunca pelo runtime.
        admin = recovery.env_of(info).get("POSTGRES_USER", "")
        require(bool(admin), "Administrador de recuperação não identificado.")
        return info, selected.database, admin
    require(scope == "lab", "Origem inválida.")
    resources()
    info = recovery.container(PROJECT, "db")
    require(
        info["State"]["Running"]
        and not info["HostConfig"]["Privileged"]
        and not info["HostConfig"].get("PortBindings"),
        "Servidor de ensaio inválido.",
    )
    require(
        info["Config"]["Image"] == recovery.POSTGRES
        and set(info["NetworkSettings"]["Networks"]) == {f"{PROJECT}_default"},
        "Imagem/rede inesperada.",
    )
    mounts = info["Mounts"]
    require(
        len(mounts) == 2
        and any(
            m.get("Name") == f"{PROJECT}_pgdata" and m["Destination"] == "/var/lib/postgresql/data"
            for m in mounts
        ),
        "Volume de banco inesperado.",
    )
    require(
        any(
            m["Type"] == "bind"
            and not m["RW"]
            and recovery.expected_bind_source(
                m["Source"], recovery.ROOT / "infra/roles-db-init.sql"
            )
            and m["Destination"] == "/docker-entrypoint-initdb.d/01-roles.sql"
            for m in mounts
        ),
        "Init SQL inesperado.",
    )
    result = (info, "aulas_roles_lab", "aulas_roles_admin")
    identity = json.loads(
        sql(
            result,
            "SELECT to_json(shobj_description(oid,'pg_database')) "
            "FROM pg_database WHERE datname=current_database()",
        )
    )
    require(identity == "aulas-ingles:roles-lab:v1", "Banco sem marcador sintético.")
    return result


def sql(target_info, statement, role=None):
    info, database, admin = target_info
    # SQL/senhas por stdin, não em argv/process list, stdout ou mensagens de erro.
    with tempfile.TemporaryFile() as stream:
        stream.write(statement.encode())
        stream.seek(0)
        return recovery.docker(
            "exec",
            "-i",
            info["Id"],
            "psql",
            "-XAt",
            "-h",
            "/var/run/postgresql",
            "-U",
            role or admin,
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            stdin=stream,
        )


def private_credentials(scope):
    root = recovery.BACKUPS
    require(not root.is_symlink() and not root.parent.is_symlink(), "Diretório redirecionado.")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(root.stat().st_mode & 0o077 == 0, "Diretório de credenciais não é privado.")
    path = root / f"roles-{scope}.json"
    if path.exists():
        require(
            not path.is_symlink() and path.stat().st_mode & 0o077 == 0,
            "Arquivo de credenciais precisa ser privado, sem links.",
        )
        data = json.loads(path.read_text())
        require(
            set(data) == set(NAMES[1:])
            and all(
                isinstance(v, str)
                and len(v) >= 32
                and v.isascii()
                and all(c.isalnum() or c in "-_" for c in v)
                for v in data.values()
            ),
            "Credenciais inválidas.",
        )
        return data
    data = {name: secrets.token_urlsafe(36) for name in NAMES[1:]}
    write_json(path, data)
    return data


def backup_gate(info, backup_path):
    require(backup_path is not None, "Produção exige backup real já restaurado no ensaio.")
    manifest = verify_bundle(backup_path)
    require(
        manifest["source"]["kind"] == "prod" and manifest["source"]["database"] == info[1],
        "Backup não pertence à origem.",
    )
    receipt = recovery.BACKUPS / "restore-receipts" / f"{manifest['bundle_id']}.json"
    require(
        receipt.is_file()
        and not receipt.is_symlink()
        and not receipt.parent.is_symlink()
        and receipt.stat().st_mode & 0o077 == 0,
        "Recibo privado de restore ausente.",
    )
    result = json.loads(receipt.read_text())
    require(
        result.get("verified") is True
        and result.get("bundle_id") == manifest["bundle_id"]
        and result.get("target") == recovery.CONFIRM_STUDY_CHECK
        and result.get("manifest") == file_info(Path(backup_path) / "manifest.json"),
        "Recibo não comprova restore deste pacote no ensaio de estudo.",
    )
    require(
        json.loads(sql(info, recovery.SNAPSHOT_SQL)) == manifest["snapshot"],
        "Origem mudou após o backup; faça novo ensaio antes de alterar papéis.",
    )


def marked_roles(info):
    current = json.loads(
        sql(
            info,
            """
      SELECT coalesce(json_agg(json_build_object('name',rolname,'marker',
        shobj_description(oid,'pg_authid'))),'[]') FROM pg_roles
      WHERE rolname IN ('aulas_owner','aulas_migrator','aulas_runtime',
                       'aulas_worker','aulas_backup')
    """,
        )
    )
    require(all(r["marker"] == MARKER for r in current), "Papel homônimo sem marcador; recusa.")
    return current


def provision(scope, backup_path=None):
    info = target(scope)
    if scope == "prod":
        backup_gate(info, backup_path)
    current = marked_roles(info)
    credentials_path = recovery.BACKUPS / f"roles-{scope}.json"
    require(not current or credentials_path.is_file(), "Papéis existentes sem credenciais locais.")
    credentials = private_credentials(scope)
    existing = {r["name"] for r in current}
    statements = ["BEGIN;"]
    for name in NAMES:
        if name not in existing:
            access = "NOLOGIN" if name == "aulas_owner" else f"LOGIN PASSWORD '{credentials[name]}'"
            statements.append(
                f"CREATE ROLE {name} {access} NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION NOBYPASSRLS;"
            )
            statements.append(f"COMMENT ON ROLE {name} IS '{MARKER}';")
    db = '"' + info[1].replace('"', '""') + '"'
    statements += [
        f"REVOKE ALL ON DATABASE {db} FROM PUBLIC;",
        f"GRANT CONNECT ON DATABASE {db} TO " + ",".join(NAMES) + ";",
        "GRANT aulas_owner TO aulas_migrator WITH ADMIN FALSE;",
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC;",
        "ALTER SCHEMA public OWNER TO aulas_owner;",
        "COMMIT;",
    ]
    sql(info, "\n".join(statements))
    env_path = recovery.BACKUPS / f"roles-{scope}.env"
    lines = [
        f"{name.removeprefix('aulas_').upper()}_DATABASE_URL="
        f"postgresql+asyncpg://{name}:{quote(password, safe='')}@db:5432/{quote(info[1], safe='')}"
        for name in NAMES[1:]
        for password in [credentials[name]]
    ]
    content = "\n".join(lines) + "\n"
    if env_path.exists():
        require(
            not env_path.is_symlink()
            and env_path.stat().st_mode & 0o077 == 0
            and env_path.read_text() == content,
            "Env existente diverge; nada sobrescrito.",
        )
    else:
        with env_path.open("x") as stream:
            os.chmod(env_path, 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())


def grants(scope, backup_path=None):
    info = target(scope)
    if scope == "prod":
        backup_gate(info, backup_path)
    require({r["name"] for r in marked_roles(info)} == set(NAMES), "Provisionamento incompleto.")
    sql(info, "BEGIN;\n" + (recovery.ROOT / "ops/roles_policy.sql").read_text() + "\nCOMMIT;")


def lab_run(purpose, *command):
    target("lab")  # Validação independente antes de qualquer processo mutável.
    credentials = private_credentials("lab")
    url = f"postgresql+asyncpg://aulas_{purpose}:{credentials[f'aulas_{purpose}']}@db:5432/aulas_roles_lab"
    # Env-file temporário privado: segredo não aparece no argv.
    with tempfile.NamedTemporaryFile(mode="w", prefix="aulas-roles-env-") as env:
        env.write(f"APP_ENV=dev\nDATABASE_PURPOSE={purpose}\nDATABASE_URL={url}\n")
        env.flush()
        return recovery.docker(
            "run",
            "--rm",
            "--network",
            f"{PROJECT}_default",
            "--env-file",
            env.name,
            "--mount",
            f"type=bind,src={recovery.ROOT / 'ops'},dst=/tools,readonly",
            recovery.HELPER,
            *command,
            timeout=180,
        )


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["resources", "provision", "grants", "prepare"])
    parser.add_argument("--scope", choices=["lab", "prod"], default="lab")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if args.scope == "prod":
        require(args.confirm == "aulas-ingles-prod", "Confirmação de produção obrigatória.")
    if args.action == "resources":
        resources()
    elif args.action == "provision":
        provision(args.scope, args.backup)
    elif args.action == "grants":
        grants(args.scope, args.backup)
    else:
        require(args.scope == "lab", "Prepare só no laboratório.")
        provision("lab")
        lab_run("migrator", "alembic", "upgrade", "head")
        lab_run("migrator", "python", "-m", "app.cli", "seed")
        grants("lab")
    print("Operação de papéis concluída sem exibir credenciais.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Operação de papéis recusada; preserve arquivos/estado para diagnóstico.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
