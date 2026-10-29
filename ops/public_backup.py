"""Backup da stack pública (EasyPanel) por SSH, no mesmo formato dos pacotes locais.

O banco é lido pelo papel limitado `aulas_backup` dentro do container do
PostgreSQL, por socket local (autenticação `trust` da imagem oficial), então
nenhuma senha é lida, transmitida ou gravada por este módulo. O volume de voz
sai pelo mesmo `voice_transfer.py` do fluxo local, executado na VM a partir de
uma cópia efêmera, em container sem rede e somente leitura.

O pacote resultante é `aulas-recovery-v2`: `verify`, `restore` em destino vazio
e `prune` tratam-no como qualquer outro. Diferença declarada: a stack pública
não para para manutenção, então a consistência banco/voz é conferida por
snapshot antes e depois da captura e o pacote não é publicado se algo mudou
(até três tentativas). O dump em si é consistente por transação.

A cópia externa exige criptografia com `age` para um destinatário cuja chave
privada não mora neste Mac; sem destinatário, o pacote fica só local.
"""

import argparse
import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import IO, TypedDict, Unpack, cast
from uuid import uuid4

from ops import recovery
from ops.recovery_archive import (
    FileInfo,
    RecoveryError,
    create_bundle,
    file_info,
    require,
    verify_bundle,
    write_json,
)

HOST_ENV = "AULAS_PUBLIC_SSH_HOST"
DEFAULT_HOST = "root@72.61.39.94"
PROJECT = "papalino"
SERVICE = "aulas-ingles"
BACKUP_ROLE = "aulas_backup"
MAX_ATTEMPTS = 3
DRIFT = "Banco público mudou durante a captura; pacote não publicado."
# BatchMode: nunca pedir senha/passphrase. StrictHostKeyChecking=yes: a chave da
# VM precisa já estar em known_hosts; um host desconhecido é recusado, não aceito.
SSH_OPTIONS = (
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "StrictHostKeyChecking=yes",
)
TOOLS = ("recovery_archive.py", "voice_transfer.py")
AGE_RECIPIENT = re.compile(r"age1[0-9a-z]{58}")


class SshOptions(TypedDict, total=False):
    stdin: IO[bytes] | int | None
    stdout: IO[bytes] | int | None
    timeout: float


class Snapshot(TypedDict):
    revision: list[str]
    counts: dict[str, int]
    audio: list[dict[str, object]]


class ContainerIdentity(TypedDict):
    id: str
    image_id: str
    image_ref: str


class CopiedFile(FileInfo):
    path: str


class EncryptedFile(CopiedFile):
    recipient: str


class CheckReport(TypedDict):
    host_configured: bool
    containers: dict[str, str]
    database: str
    backup_role: str
    revision: list[str]
    age_available: bool


def checked_snapshot(value: object) -> Snapshot:
    if not isinstance(value, dict):
        raise RecoveryError("Snapshot remoto incompleto.")
    revision, counts, audio = value.get("revision"), value.get("counts"), value.get("audio")
    if (
        not isinstance(revision, list) or not revision
        or not all(isinstance(item, str) and item for item in revision)
        or not isinstance(counts, dict)
        or not all(isinstance(key, str) and type(count) is int and count >= 0
                   for key, count in counts.items())
        or not isinstance(audio, list) or not all(isinstance(item, dict) for item in audio)
    ):
        raise RecoveryError("Snapshot remoto incompleto.")
    # Preservar o objeto inteiro, inclusive extensões, para comparar antes/depois da captura.
    return cast(Snapshot, value)


def container(service: str) -> str:
    return f"{PROJECT}_{SERVICE}-{service}-1"


def voice_volume() -> str:
    return f"{PROJECT}_{SERVICE}_speaking_data"


def api_image() -> str:
    return f"{PROJECT}_{SERVICE}-api"


def receipts_dir() -> Path:
    return recovery.BACKUPS / "public-receipts"


def resolve_host(explicit: str | None = None) -> str:
    host = explicit or os.environ.get(HOST_ENV) or DEFAULT_HOST
    require(
        re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+", host) is not None,
        "Destino SSH inválido; use usuario@host.",
    )
    return host


def ssh(
    host: str, remote: str, *, stdin: IO[bytes] | int | None = None,
    stdout: IO[bytes] | int | None = None, timeout: float = 600,
) -> bytes:
    """Executa um comando remoto. stderr nunca é repassado: pode conter caminhos ou dados."""
    try:
        result = subprocess.run(
            ["ssh", *SSH_OPTIONS, host, remote],
            stdin=stdin,
            stdout=stdout or subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=True,
        )
        return result.stdout or b""
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecoveryError("Comando remoto falhou; nenhum sucesso foi confirmado.") from exc


def scp(host: str, sources: Iterable[str | Path], remote_dir: str) -> None:
    try:
        subprocess.run(
            ["scp", "-q", *SSH_OPTIONS, *map(str, sources), f"{host}:{remote_dir}/"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=120,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecoveryError("Cópia das ferramentas para a VM falhou.") from exc


def in_db(host: str, command: str, **kwargs: Unpack[SshOptions]) -> bytes:
    # `sh -c` roda dentro do container: $POSTGRES_DB é resolvido lá, nunca aqui.
    return ssh(host, f"docker exec -i {container('db')} sh -c {shlex.quote(command)}", **kwargs)


def psql(host: str, sql: str, **kwargs: Unpack[SshOptions]) -> bytes:
    return in_db(
        host,
        f'psql -U {BACKUP_ROLE} -d "$POSTGRES_DB" -XAt -v ON_ERROR_STOP=1 -c {shlex.quote(sql)}',
        **kwargs,
    )


def snapshot(host: str) -> Snapshot:
    try:
        value = json.loads(psql(host, recovery.SNAPSHOT_SQL))
    except ValueError as exc:
        raise RecoveryError("Snapshot remoto inválido.") from exc
    return checked_snapshot(value)


def database_name(host: str) -> str:
    name = psql(host, "SELECT current_database()").decode().strip()
    require(re.fullmatch(r"[A-Za-z0-9_]+", name) is not None, "Nome de banco remoto inesperado.")
    return name


def inventory(host: str) -> dict[str, ContainerIdentity]:
    """Identidades imutáveis dos containers e imagens; sem env, sem segredos."""
    names = [container("db"), container("api"), container("worker")]
    raw = ssh(
        host,
        "docker inspect --format '{{.Id}} {{.Image}} {{.Config.Image}}' " + " ".join(names),
    ).decode()
    rows = [line.split() for line in raw.strip().splitlines()]
    require(
        len(rows) == len(names) and all(len(row) == 3 for row in rows),
        "Containers da stack pública ausentes ou inesperados.",
    )
    return {
        name: {"id": row[0], "image_id": row[1], "image_ref": row[2]}
        for name, row in zip(names, rows, strict=True)
    }


def local_pg_restore_list(dump: Path) -> None:
    """Valida o índice do dump com a imagem de PostgreSQL já usada pelas stacks locais."""
    with dump.open("rb") as stream:
        recovery.docker(
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--entrypoint",
            "pg_restore",
            recovery.POSTGRES,
            "--list",
            stdin=stream,
        )


def export_voice(host: str, stream: IO[bytes]) -> None:
    """Mesmo exportador validado do fluxo local, rodando na VM a partir de cópia efêmera."""
    tools = f"/tmp/aulas-ingles-backup-tools-{uuid4().hex}"
    # 755/644: o container roda como uid 10001 e precisa ler os scripts que o
    # root copiou. São arquivos públicos do repositório, não segredos.
    ssh(host, f"mkdir -m 755 {tools}")
    try:
        scp(host, [recovery.ROOT / "ops" / name for name in TOOLS], tools)
        ssh(host, f"chmod 644 {tools}/*.py")
        ssh(
            host,
            " ".join(
                [
                    "docker run --rm -i --network none --read-only --cap-drop ALL",
                    "--security-opt no-new-privileges --user 10001:10001",
                    "-e PYTHONDONTWRITEBYTECODE=1",
                    f"--mount type=bind,src={tools},dst=/tools,readonly",
                    f"--mount type=volume,src={voice_volume()},dst=/voice,readonly",
                    f"--entrypoint python {api_image()} /tools/voice_transfer.py export",
                ]
            ),
            stdout=stream,
            timeout=900,
        )
    finally:
        # Se a limpeza falhar, só ferramentas públicas do repositório ficam para trás.
        with contextlib.suppress(RecoveryError):
            ssh(host, f"rm -rf {tools}")


def worktree_info() -> dict[str, str | bool]:
    return {
        "worktree_head": recovery.run(["git", "rev-parse", "HEAD"]).decode().strip(),
        "worktree_dirty": bool(recovery.run(["git", "status", "--porcelain"])),
    }


def capture(host: str, attempts: int = MAX_ATTEMPTS) -> Path:
    """Publica um pacote v2 da stack pública ou levanta RecoveryError, sem parciais anunciados."""
    recovery.local_daemon()
    containers = inventory(host)
    database = database_name(host)

    def do_capture(staging: Path) -> dict[str, object]:
        before = snapshot(host)
        with (staging / "database.dump").open("xb") as stream:
            in_db(
                host,
                f'pg_dump -U {BACKUP_ROLE} -d "$POSTGRES_DB" -Fc',
                stdout=stream,
                timeout=900,
            )
        local_pg_restore_list(staging / "database.dump")
        with (staging / "voice.tar").open("xb") as stream:
            export_voice(host, stream)
        require(snapshot(host) == before, DRIFT)
        return {
            "snapshot": before,
            "source": {
                "kind": "public",
                "project": PROJECT,
                "service": SERVICE,
                "database": database,
                "db_container_id": containers[container("db")]["id"],
                "db_image_id": containers[container("db")]["image_id"],
                "voice_volume": voice_volume(),
                "consistency": "online-snapshot-check",
            },
            "application": {
                "deployed_containers": [
                    {"service": service, **containers[container(service)]}
                    for service in ("api", "worker")
                ],
                "tools_image_id": None,
                **worktree_info(),
                "note": "Captura online pela VM; a worktree local não representa o deploy. "
                "Use os IDs de imagem e a revisão do snapshot.",
            },
        }

    for attempt in range(1, attempts + 1):
        try:
            return create_bundle(recovery.BACKUPS, do_capture)
        except RecoveryError as exc:
            if str(exc) != DRIFT or attempt == attempts:
                raise
    raise RecoveryError(DRIFT)


def read_recipient(path: str | Path) -> str:
    recipient_path = Path(path)
    require(
        recipient_path.is_file() and not recipient_path.is_symlink(),
        "Arquivo do destinatário age ausente ou é um link.",
    )
    recipient = recipient_path.read_text(encoding="utf-8").strip()
    require(
        AGE_RECIPIENT.fullmatch(recipient) is not None,
        "Destinatário age inválido; esperado uma chave pública age1....",
    )
    return recipient


def encrypt(bundle: Path, recipient: str, out_dir: str | Path) -> EncryptedFile:
    """tar do pacote publicado cifrado para o destinatário; a chave privada fica fora daqui."""
    require(shutil.which("age") is not None, "Instale `age` para criptografar (brew install age).")
    out = Path(out_dir)
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(
        not out.is_symlink() and out.stat().st_mode & 0o077 == 0,
        "Diretório de pacotes criptografados deve ser privado (700) e não pode ser link.",
    )
    target = out / f"{bundle.name}.tar.age"
    require(not target.exists(), "Pacote criptografado já existe; nada foi sobrescrito.")
    created = False
    try:
        with target.open("xb") as stream:
            created = True
            os.chmod(target, 0o600)
            with subprocess.Popen(
                ["tar", "-C", str(bundle.parent), "-cf", "-", bundle.name],
                # BSD tar no macOS acrescenta AppleDouble (._*), invalidando o pacote
                # após decifrar/extrair. GNU tar ignora esta variável.
                env={**os.environ, "COPYFILE_DISABLE": "1"},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as tar:
                assert tar.stdout is not None  # PIPE definido explicitamente acima.
                sealed = subprocess.run(
                    ["age", "-r", recipient],
                    stdin=tar.stdout,
                    stdout=stream,
                    stderr=subprocess.PIPE,
                    timeout=900,
                )
                tar.stdout.close()
                tar.wait(timeout=120)
                ok = sealed.returncode == 0 and tar.returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        if created:
            target.unlink(missing_ok=True)
        raise RecoveryError("Criptografia falhou; nenhum pacote cifrado foi publicado.") from exc
    if not ok:
        target.unlink(missing_ok=True)
        raise RecoveryError("Criptografia falhou; nenhum pacote cifrado foi publicado.")
    return {"path": str(target), **file_info(target), "recipient": recipient}


def copy_external(encrypted: str | Path, destination_dir: str | Path) -> CopiedFile:
    """Só cópia cifrada sai do Mac; o destino pode ser uma pasta sincronizada ou montada."""
    source = Path(encrypted)
    require(
        source.name.endswith(".tar.age"), "Cópia externa exige pacote criptografado (.tar.age)."
    )
    destination = Path(destination_dir)
    require(destination.is_dir() and not destination.is_symlink(), "Destino externo inexistente.")
    target = destination / source.name
    require(not target.exists(), "Cópia externa já existe; nada foi sobrescrito.")
    expected = file_info(source)
    try:
        # A criação exclusiva mantém a recusa de sobrescrita mesmo com duas cópias concorrentes.
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            os.chmod(target, 0o600)
            shutil.copyfileobj(incoming, outgoing)
            outgoing.flush()
            os.fsync(outgoing.fileno())
    except OSError as exc:
        raise RecoveryError(
            "Cópia externa falhou; preserve o destino parcial para diagnóstico."
        ) from exc
    require(
        file_info(target) == expected == file_info(source),
        "Cópia externa divergente da origem.",
    )
    return {"path": str(target), **file_info(target)}


def write_receipt(
    manifest: Mapping[str, object], encrypted: EncryptedFile | None = None,
    external: CopiedFile | None = None,
) -> Path:
    snapshot_data = checked_snapshot(manifest.get("snapshot"))
    audio, application = manifest.get("audio_files"), manifest.get("application")
    if not isinstance(audio, dict) or not isinstance(application, dict):
        raise RecoveryError("Inventário/aplicação do manifesto inválidos.")
    directory = receipts_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    receipt = {
        "bundle_id": manifest["bundle_id"],
        "created_at": manifest["created_at"],
        "revision": snapshot_data["revision"],
        "counts": snapshot_data["counts"],
        "artifacts": manifest["artifacts"],
        "audio_file_count": len(audio),
        "source": manifest["source"],
        "deployed_containers": application["deployed_containers"],
        "encrypted": encrypted,
        "external_copy": external,
    }
    path = directory / f"{manifest['bundle_id']}.json"
    write_json(path, receipt)
    return path


def check(host: str) -> CheckReport:
    """Pré-voo sem captura: acesso, containers, papel, revisão e ferramentas locais."""
    recovery.local_daemon()
    containers = inventory(host)
    revision = snapshot(host)["revision"]
    return {
        "host_configured": True,
        "containers": {name: info["image_ref"] for name, info in containers.items()},
        "database": database_name(host),
        "backup_role": BACKUP_ROLE,
        "revision": revision,
        "age_available": shutil.which("age") is not None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", help=f"usuario@host da VM (padrão: ${HOST_ENV} ou documentado)")
    commands = parser.add_subparsers(dest="command", required=True)
    run_capture = commands.add_parser("capture", help="Publica um pacote v2 da stack pública.")
    run_capture.add_argument("--recipient-file", help="Arquivo com a chave pública age1... .")
    run_capture.add_argument(
        "--encrypted-dir",
        default=str(recovery.BACKUPS.parent / "encrypted"),
        help="Onde gravar o .tar.age (padrão: backups/encrypted).",
    )
    run_capture.add_argument("--copy-to", help="Diretório externo que recebe só o .tar.age.")
    run_capture.add_argument("--json", action="store_true")
    run_check = commands.add_parser("check", help="Pré-voo sem captura.")
    run_check.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        host = resolve_host(args.host)
        if args.command == "check":
            report = check(host)
            print(
                json.dumps(report, indent=2, sort_keys=True) if args.json else _render_check(report)
            )
            return 0
        require(
            not args.copy_to or args.recipient_file,
            "Cópia externa exige --recipient-file: só pacote cifrado sai do Mac.",
        )
        recipient = read_recipient(args.recipient_file) if args.recipient_file else None
        bundle = capture(host)
        manifest = verify_bundle(bundle)
        snapshot_data = checked_snapshot(manifest.get("snapshot"))
        encrypted = encrypt(bundle, recipient, args.encrypted_dir) if recipient else None
        external = None
        if args.copy_to:
            if encrypted is None:
                raise RecoveryError("Cópia externa exige pacote cifrado confirmado.")
            external = copy_external(encrypted["path"], args.copy_to)
        receipt = write_receipt(manifest, encrypted, external)
        summary = {
            "bundle": str(bundle),
            "revision": snapshot_data["revision"],
            "counts": snapshot_data["counts"],
            "encrypted": encrypted["path"] if encrypted else None,
            "external_copy": external["path"] if external else None,
            "receipt": str(receipt),
        }
        if args.json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            print(f"Pacote publicado e verificado: {bundle}")
            print(f"Revisão do schema: {', '.join(snapshot_data['revision'])}")
            if encrypted:
                print(f"Cifrado para cópia externa: {encrypted['path']}")
            else:
                print("Sem destinatário age: pacote só local, não copie para fora sem cifrar.")
            if external:
                print(f"Cópia externa: {external['path']}")
            print(f"Recibo: {receipt}")
        return 0
    except RecoveryError as exc:
        print(
            f"Operação recusada: {exc} Parciais são preservados; nada foi anunciado como válido.",
            file=sys.stderr,
        )
        return 1


def _render_check(report: CheckReport) -> str:
    lines = [
        f"Banco: {report['database']} (papel {report['backup_role']})",
        f"Revisão Alembic: {', '.join(report['revision'])}",
        "Containers:",
        *(f"  {name}: {image}" for name, image in report["containers"].items()),
        f"age disponível no Mac: {'sim' if report['age_available'] else 'não (brew install age)'}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
