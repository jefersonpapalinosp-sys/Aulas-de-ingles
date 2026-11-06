"""Release por imagens preservadas; executado somente pelo comando SSH instalado."""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from ops.recovery_archive import RecoveryError, require

SERVICES = ("api", "worker", "web")
BUILD_SERVICES = ("api", "worker", "web", "migrate", "permissions", "seed", "db")
HEALTH = (
    "import json,sys,urllib.request; "
    'r=urllib.request.Request("http://localhost:8000/api/health",'
    'headers={"X-Forwarded-Proto":"https"}); '
    "v=json.load(urllib.request.urlopen(r,timeout=5)); "
    'sys.exit(0 if v.get("status")=="ok" and v.get("db")=="up" '
    'and v.get("schema")=="compatible" else 1)'
)


def run(args: Sequence[str], *, cwd: Path | None = None, timeout: int = 900) -> bytes:
    """Limita o grupo inteiro de processos; não imprime env, SQL ou stderr arbitrário."""
    with subprocess.Popen(
        args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True
    ) as process:
        try:
            output, _ = process.communicate(timeout=timeout)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
            raise
        require(process.returncode == 0, "Etapa operacional falhou; consulte a fase registrada.")
        return output


def save(path: Path, data: dict[str, Any]) -> None:
    require(not path.is_symlink(), "Estado não pode ser link.")
    fd, name = tempfile.mkstemp(prefix=".release-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def extract(archive: Path, destination: Path) -> None:
    """Somente arquivos regulares do git archive; nenhum link ou arquivo privado."""
    total = 0
    with tarfile.open(archive, "r:") as source:
        for member in source:
            parts = Path(member.name).parts
            require(
                parts and not Path(member.name).is_absolute() and ".." not in parts,
                "Arquivo fora da release.",
            )
            require(member.isdir() or member.isfile(), "Links não são aceitos na release.")
            require(
                not any(
                    p in {".git", "secrets", "backups"}
                    or (p.startswith(".env") and not p.endswith(".example"))
                    for p in parts
                ),
                "Arquivo privado não pode integrar a release.",
            )
            target = destination.joinpath(*parts)
            total += member.size
            require(total <= 512 * 1024 * 1024, "Release excede limite operacional.")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = source.extractfile(member)
            require(stream is not None, "Arquivo sem conteúdo.")
            assert stream is not None
            with stream, target.open("xb") as output:
                while chunk := stream.read(1024 * 1024):
                    output.write(chunk)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)


class Releases:
    def __init__(self, config: dict[str, Any]):
        self.project = config["project"]
        require(re.fullmatch(r"[a-z][a-z0-9_-]{1,60}", self.project), "Projeto inválido.")
        self.repo = Path(config["repository"])
        self.state = Path(config["state"])
        self.env = Path(config["env_file"])
        self.override = Path(config["override_file"])
        self.code = Path(config["existing_code"])
        require(
            all(
                p.is_absolute() and not p.is_symlink()
                for p in (self.repo, self.state, self.env, self.override, self.code)
            ),
            "Caminho inválido.",
        )
        require(
            self.env.is_file() and self.env.stat().st_mode & 0o077 == 0,
            "Configuração privada deve ter permissão 0600.",
        )
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        (self.state / "releases").mkdir(mode=0o700, exist_ok=True)

    def phase(self, name: str) -> None:
        save(self.state / "phase.json", {"phase": name, "recorded_at": time.time()})
        print(json.dumps({"phase": name}), flush=True)

    def compose(self, release: Path, *args: str, images: bool = True) -> list[str]:
        command = [
            "docker",
            "compose",
            "-p",
            self.project,
            "--env-file",
            str(self.env),
            "-f",
            str(release / "infra/easypanel/compose.yml"),
            "-f",
            str(self.override),
        ]
        if images:
            command += ["-f", str(release / "images.json")]
        return [*command, *args]

    def receipt(self, name: str) -> dict[str, Any]:
        path = self.state / f"{name}.json"
        require(
            path.is_file() and not path.is_symlink(), "Adote a release atual antes de publicar."
        )
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise RecoveryError("Recibo inválido.")
        require(
            isinstance(value, dict) and re.fullmatch(r"[a-z0-9-]{1,90}", value.get("release", "")),
            "Recibo inválido.",
        )
        return value

    def location(self, record: dict[str, Any]) -> Path:
        path = self.state / "releases" / str(record["release"])
        require(path.is_dir() and not path.is_symlink(), "Release preservada ausente.")
        return path

    def images(self) -> dict[str, str]:
        result = {}
        for service in SERVICES:
            raw = run(
                ["docker", "inspect", "--format", "{{.Image}}", f"{self.project}-{service}-1"]
            )
            identity = raw.decode().strip()
            require(re.fullmatch(r"sha256:[a-f0-9]{64}", identity), "Imagem inválida.")
            result[service] = identity
        return result

    def preserve(self, images: dict[str, str], release: str) -> None:
        for service, identity in images.items():
            run(["docker", "tag", identity, f"aulas-preserved/{self.project}-{service}:{release}"])

    def adopt(self) -> None:
        require(not (self.state / "current.json").exists(), "Release já adotada.")
        name = "baseline-" + uuid4().hex
        release = self.state / "releases" / name
        target = release / "infra/easypanel/compose.yml"
        target.parent.mkdir(parents=True)
        target.write_bytes((self.code / "infra/easypanel/compose.yml").read_bytes())
        images = self.images()
        self.preserve(images, name)
        save(release / "images.json", {"services": {s: {"image": v} for s, v in images.items()}})
        run(self.compose(release, "exec", "-T", "api", "python", "-c", HEALTH), timeout=15)
        save(self.state / "current.json", {"release": name, "images": images})

    def deploy(self, sha: str) -> None:
        require(re.fullmatch(r"[a-f0-9]{40}", sha), "SHA completo obrigatório.")
        require(
            not (self.state / "pending.json").exists(),
            "Release pendente; resolver ou reverter primeiro.",
        )
        previous = self.receipt("current")
        require(self.images() == previous["images"], "Stack diverge do recibo atual.")
        self.phase("fetch-approved-main")
        run(["git", "fetch", "origin", "main"], cwd=self.repo, timeout=120)
        run(["git", "merge-base", "--is-ancestor", sha, "origin/main"], cwd=self.repo)
        name = sha + "-" + uuid4().hex[:12]
        release = self.state / "releases" / name
        release.mkdir(mode=0o700)
        archive = release / "source.tar"
        run(["git", "archive", "--format=tar", "--output", str(archive), sha], cwd=self.repo)
        extract(archive, release)
        archive.unlink()
        self.preserve(previous["images"], previous["release"])
        tags = {s: f"aulas-candidate/{self.project}-{s}:{name}" for s in BUILD_SERVICES}
        save(release / "images.json", {"services": {s: {"image": tag} for s, tag in tags.items()}})
        self.phase("build-before-mutation")
        run(self.compose(release, "build"), timeout=1200)
        identities = {
            s: run(["docker", "image", "inspect", "--format", "{{.Id}}", tag]).decode().strip()
            for s, tag in tags.items()
        }
        require(
            all(re.fullmatch(r"sha256:[a-f0-9]{64}", v) for v in identities.values()),
            "Imagem ausente.",
        )
        self.phase("critical-vulnerability-gate")
        for identity in sorted(set(identities.values())):
            run(
                [
                    "trivy",
                    "image",
                    "--quiet",
                    "--scanners",
                    "vuln",
                    "--severity",
                    "CRITICAL",
                    "--exit-code",
                    "1",
                    identity,
                ],
                timeout=300,
            )
        save(
            release / "images.json", {"services": {s: {"image": v} for s, v in identities.items()}}
        )
        # O arquivo público de assets deve ser migrado uma única vez pelo operador.
        run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--user",
                "101:101",
                "--mount",
                f"type=volume,src={self.project}_web_assets,dst=/var/lib/aulas-web",
                "--entrypoint",
                "sh",
                identities["web"],
                "-ec",
                "test -w /var/lib/aulas-web",
            ]
        )
        save(self.state / "previous.json", previous)
        candidate = {"release": name, "sha": sha, "images": {s: identities[s] for s in SERVICES}}
        save(self.state / "pending.json", candidate)
        self.phase("drain-worker-and-migrate")
        run(self.compose(release, "stop", "worker"), timeout=180)
        run(self.compose(release, "run", "--rm", "--no-deps", "--pull", "never", "migrate"))
        run(self.compose(release, "run", "--rm", "--no-deps", "--pull", "never", "permissions"))
        self.phase("start-verified-images")
        run(
            self.compose(
                release,
                "up",
                "-d",
                "--no-deps",
                "--no-build",
                "--pull",
                "never",
                "--wait",
                "--wait-timeout",
                "180",
                *SERVICES,
            ),
            timeout=240,
        )
        run(self.compose(release, "exec", "-T", "api", "python", "-c", HEALTH), timeout=15)
        run(self.compose(release, "run", "--rm", "--no-deps", "--pull", "never", "seed"))
        require(self.images() == candidate["images"], "Imagens em execução divergem da release.")
        save(self.state / "current.json", candidate)
        (self.state / "pending.json").unlink()
        self.phase("release-ready")

    def rollback(self) -> None:
        started = time.monotonic()
        previous = self.receipt("previous")
        release = self.location(previous)
        self.phase("rollback-compatibility-probe")
        probe = (
            run(self.compose(release, "run", "-d", "--no-deps", "--pull", "never", "api"))
            .decode()
            .strip()
        )
        require(re.fullmatch(r"[a-f0-9]{64}", probe), "Probe inválido.")
        try:
            for attempt in range(20):
                try:
                    run(["docker", "exec", probe, "python", "-c", HEALTH], timeout=10)
                    break
                except RecoveryError:
                    if attempt == 19:
                        raise
                    time.sleep(2)
        finally:
            run(["docker", "rm", "-f", probe])
        self.phase("rollback-images-without-migration")
        run(self.compose(release, "stop", "worker"), timeout=180)
        run(
            self.compose(
                release,
                "up",
                "-d",
                "--no-deps",
                "--no-build",
                "--pull",
                "never",
                "--wait",
                "--wait-timeout",
                "120",
                *SERVICES,
            ),
            timeout=180,
        )
        run(self.compose(release, "exec", "-T", "api", "python", "-c", HEALTH), timeout=15)
        require(
            self.images() == previous["images"], "Rollback não confirmou as imagens preservadas."
        )
        save(self.state / "current.json", previous)
        (self.state / "pending.json").unlink(missing_ok=True)
        print(json.dumps({"rollback_seconds": round(time.monotonic() - started, 3)}))


@contextlib.contextmanager
def lock(path: Path) -> Iterator[None]:
    import fcntl

    require(not path.is_symlink(), "Lock inválido.")
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
