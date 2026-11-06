"""Restaura banco e voz em uma stack pública nova, parada e explicitamente confirmada."""

import argparse
import json
import re
import shlex
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Unpack
from uuid import uuid4

from ops import public_backup as remote
from ops import recovery
from ops.recovery_archive import (
    ARTIFACTS,
    MAX_TOTAL,
    RecoveryError,
    audio_inventory,
    file_info,
    require,
    verify_bundle,
    write_json,
)


def unseal(encrypted: Path, identity: Path, output: Path) -> Path:
    require(encrypted.is_file() and not encrypted.is_symlink(), "Cópia cifrada inválida.")
    require(identity.is_file() and not identity.is_symlink(), "Identidade age inválida.")
    require(not output.exists() and not output.is_symlink(), "Destino de abertura deve ser novo.")
    output.mkdir(mode=0o700, parents=True)
    # Temporário privado; nunca extrair nomes, permissões ou links fornecidos pelo tar.
    with tempfile.TemporaryFile(dir=output) as plain:
        result = subprocess.run(
            ["age", "--decrypt", "--identity", str(identity), str(encrypted)],
            stdout=plain,
            stderr=subprocess.DEVNULL,
            timeout=900,
        )
        require(result.returncode == 0, "Decifragem recusada.")
        require(
            0 < plain.tell() <= 2 * MAX_TOTAL + 64 * 1024 * 1024,
            "Pacote decifrado excede o limite.",
        )
        plain.seek(0)
        bundle = None
        seen = set()
        with tarfile.open(fileobj=plain, mode="r:") as archive:
            for member in archive:
                parts = member.name.rstrip("/").split("/")
                from ops.recovery_prune import BUNDLE_RE

                require(BUNDLE_RE.fullmatch(parts[0]), "Identidade interna inválida.")
                if bundle is None:
                    bundle = output / parts[0]
                    bundle.mkdir(mode=0o700)
                require(parts[0] == bundle.name, "Mais de um pacote no arquivo.")
                if member.isdir() and len(parts) == 1:
                    continue
                require(
                    len(parts) == 2
                    and parts[1] in {*ARTIFACTS, "manifest.json"}
                    and member.isfile()
                    and parts[1] not in seen,
                    "Entrada insegura no pacote.",
                )
                limit = 32 * 1024 * 1024 if parts[1] == "manifest.json" else MAX_TOTAL
                require(0 < member.size <= limit, "Artefato excede o limite.")
                seen.add(parts[1])
                source = archive.extractfile(member)
                if source is None:
                    raise RecoveryError("Artefato sem conteúdo regular.")
                with source, (bundle / parts[1]).open("xb") as dest:
                    remaining = member.size
                    while remaining:
                        chunk = source.read(min(remaining, 1024 * 1024))
                        require(chunk, "Artefato truncado.")
                        dest.write(chunk)
                        remaining -= len(chunk)
        require(bundle is not None, "Pacote vazio.")
        assert bundle is not None
        verify_bundle(bundle)
        return bundle


class Destination:
    def __init__(self, host: str, project: str) -> None:
        require(
            re.fullmatch(r"aulas-dr-[a-z0-9][a-z0-9-]{0,35}", project),
            "Use uma stack nova com prefixo aulas-dr-.",
        )
        self.host = remote.resolve_host(host)
        self.project = project
        self.db = f"{project}-db-1"
        self.voice = f"{project}_speaking_data"
        self.image = ""

    def call(self, command: str, **kwargs: Unpack[remote.SshOptions]) -> bytes:
        return remote.ssh(self.host, command, **kwargs)

    def sql(self, sql: str) -> Any:
        command = 'psql -U aulas_admin -d "$POSTGRES_DB" -XAt -v ON_ERROR_STOP=1 -c '
        return json.loads(
            self.call(f"docker exec {self.db} sh -c " + shlex.quote(command + shlex.quote(sql)))
        )

    def check(self) -> None:
        for service in ("db", "api", "worker", "web"):
            name = f"{self.project}-{service}-1"
            # Inspeção restrita: Config.Env e segredos não atravessam o transporte.
            template = "\n".join(
                "{{json ." + field + "}}"
                for field in ("State.Running", "Config.Labels", "Mounts", "Image")
            )
            lines = (
                self.call(f"docker inspect --format {shlex.quote(template)} {name}")
                .decode()
                .splitlines()
            )
            require(len(lines) == 4, "Container de destino ausente.")
            running, labels, mounts, image = map(json.loads, lines)
            require(
                labels.get("com.docker.compose.project") == self.project
                and labels.get("com.docker.compose.service") == service,
                "Identidade Compose divergente.",
            )
            require(running is (service == "db"), "Somente o banco de destino pode estar ligado.")
            if service == "db":
                expected, mountpoint = f"{self.project}_pgdata", "/var/lib/postgresql/data"
            elif service in {"api", "worker"}:
                expected, mountpoint = self.voice, "/app/data/speaking"
                self.image = image if service == "api" else self.image
            else:
                continue
            require(
                any(
                    m.get("Type") == "volume"
                    and m.get("Name") == expected
                    and m.get("Destination") == mountpoint
                    for m in mounts
                ),
                "Volume do destino diverge.",
            )
            volume = json.loads(
                self.call("docker volume inspect --format '{{json .Labels}}' " + expected)
            )
            require(
                volume.get("com.docker.compose.project") == self.project,
                "Volume não pertence à stack nova.",
            )
        require(
            self.sql(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid() AND backend_type='client backend'"
            )
            == 0,
            "Destino tem conexões ativas; interrompa os clientes.",
        )

    def transfer(self, tools: str, action: str, **kwargs: Unpack[remote.SshOptions]) -> None:
        require(action in {"import", "export"}, "Ação de voz inválida.")
        flags = (
            "--user 10001:10001"
            if action == "export"
            else "--user 0:0 --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER"
        )
        readonly = ",readonly" if action == "export" else ""
        self.call(
            f"docker run --rm -i --network none --read-only --cap-drop ALL "
            f"--security-opt no-new-privileges {flags} -e PYTHONDONTWRITEBYTECODE=1 "
            f"--mount type=bind,src={tools},dst=/tools,readonly "
            f"--mount type=volume,src={self.voice},dst=/voice{readonly} "
            f"--entrypoint python {self.image} /tools/voice_transfer.py {action}",
            **kwargs,
        )


def restore(bundle: Path, destination: Destination, confirm: str, receipts: Path) -> Path:
    require(
        confirm == f"{destination.host}/{destination.project}", "Confirmação de destino divergente."
    )
    manifest = verify_bundle(bundle)  # Nenhuma mutação remota antes da integridade local.
    source = manifest.get("source")
    require(isinstance(source, dict) and source.get("kind") == "public", "Use um backup público.")
    started = time.monotonic()
    destination.check()
    application = manifest.get("application")
    deployed = application.get("deployed_containers") if isinstance(application, dict) else None
    require(
        isinstance(deployed, list)
        and any(
            isinstance(item, dict)
            and item.get("service") == "api"
            and item.get("image_id") == destination.image
            for item in deployed
        ),
        "Imagem da API não corresponde ao backup; prepare a versão registrada.",
    )
    lock = (
        destination.call(
            f"docker create --name aulas-recovery-{destination.project}-lock --network none "
            f"--label org.aulas.purpose=recovery-lock --entrypoint true {destination.image}"
        )
        .decode()
        .strip()
    )
    require(re.fullmatch(r"[a-f0-9]{64}", lock), "Identidade do lock inválida.")
    tools = f"/tmp/aulas-public-restore-{uuid4().hex}"
    try:
        destination.check()
        require(destination.sql(recovery.EMPTY_SQL) == 0, "Banco de destino não está vazio.")
        destination.call(f"mkdir -m 755 {tools}")
        remote.scp(
            destination.host,
            [recovery.ROOT / "ops" / name for name in (*remote.TOOLS, "roles_policy.sql")],
            tools,
        )
        destination.call(f"chmod 644 {tools}/*")
        with tempfile.TemporaryFile() as stream:
            destination.transfer(tools, "export", stdout=stream)
            stream.seek(0)
            with tarfile.open(fileobj=stream, mode="r:") as archive:
                require(next(iter(archive), None) is None, "Voz de destino não está vazia.")
        with (bundle / "database.dump").open("rb") as stream:
            command = (
                'pg_restore -U aulas_migrator --role aulas_owner -d "$POSTGRES_DB" '
                "--single-transaction --exit-on-error --no-owner --no-privileges"
            )
            destination.call(
                f"docker exec -i {destination.db} sh -c {shlex.quote(command)}",
                stdin=stream,
                timeout=900,
            )
        with (recovery.ROOT / "ops/roles_policy.sql").open("rb") as stream:
            command = 'psql -U aulas_admin -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -1'
            destination.call(
                f"docker exec -i {destination.db} sh -c {shlex.quote(command)}", stdin=stream
            )
        with (bundle / "voice.tar").open("rb") as stream:
            destination.transfer(tools, "import", stdin=stream)
        require(
            destination.sql(recovery.SNAPSHOT_SQL) == manifest["snapshot"],
            "Snapshot restaurado diverge do backup.",
        )
        with tempfile.TemporaryDirectory() as temp:
            voice = Path(temp) / "voice.tar"
            with voice.open("xb") as stream:
                destination.transfer(tools, "export", stdout=stream)
            require(audio_inventory(voice) == manifest["audio_files"], "Voz restaurada divergente.")
        destination.check()
        require(not receipts.is_symlink(), "Recibos não podem ser link.")
        receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
        receipt = receipts / f"{manifest['bundle_id']}-{uuid4().hex}.json"
        write_json(
            receipt,
            {
                "bundle_id": manifest["bundle_id"],
                "verified": True,
                "manifest": file_info(bundle / "manifest.json"),
                "seconds": round(time.monotonic() - started, 3),
                "project": destination.project,
                "traffic_enabled": False,
            },
        )
        return receipt
    finally:
        # Dados parcialmente restaurados ficam intactos e o tráfego continua parado.
        destination.call(f"docker rm {lock}")
        destination.call(f"rm -rf {tools}")


def main(argv: Sequence[str] | None = None) -> int:
    import os

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    decrypt = commands.add_parser("unseal")
    decrypt.add_argument("encrypted", type=Path)
    decrypt.add_argument("--identity", type=Path, required=True)
    decrypt.add_argument("--output", type=Path, required=True)
    load = commands.add_parser("restore")
    load.add_argument("bundle", type=Path)
    load.add_argument("--host", required=True)
    load.add_argument("--project", required=True)
    load.add_argument("--confirm", required=True)
    load.add_argument("--receipts", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "unseal":
            print(unseal(args.encrypted, args.identity, args.output))
        else:
            receipt = restore(
                args.bundle, Destination(args.host, args.project), args.confirm, args.receipts
            )
            print(f"Par banco/voz restaurado e verificado; tráfego parado. Recibo: {receipt}")
        return 0
    except Exception as exc:
        from ops.diagnostics import diagnostic

        diagnostic("public_restore", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
