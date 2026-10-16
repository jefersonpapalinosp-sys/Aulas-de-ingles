"""Constrói a imagem anterior fixa para provar rollback só da aplicação."""

import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from ops.recovery import ROOT
from ops.recovery_archive import RecoveryError, require

REVISION = "d0b1f8c"
IMAGE = "aulas-ingles-rollback42:local"


def git(*args: str, stdout=None) -> bytes:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            stdout=stdout or subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecoveryError(
            "Revisão anterior fixa não está disponível localmente."
        ) from exc
    return result.stdout or b""


def build() -> dict[str, str]:
    full_revision = git("rev-parse", f"{REVISION}^{{commit}}").decode().strip()
    require(full_revision.startswith(REVISION), "Revisão anterior divergente.")
    git("merge-base", "--is-ancestor", full_revision, "HEAD")
    with tempfile.TemporaryDirectory(prefix="aulas-rollback42-") as temporary:
        root = Path(temporary)
        archive = root / "source.tar"
        source = root / "source"
        source.mkdir()
        with archive.open("xb") as stream:
            git("archive", "--format=tar", full_revision, stdout=stream)
        with tarfile.open(archive, "r:") as package:
            package.extractall(source, filter="data")
        try:
            subprocess.run(
                [
                    "docker",
                    "build",
                    "-f",
                    str(source / "backend" / "Dockerfile.prod"),
                    "-t",
                    IMAGE,
                    str(source),
                ],
                cwd=ROOT,
                capture_output=True,
                check=True,
                timeout=900,
            )
            image_id = (
                subprocess.run(
                    ["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE],
                    cwd=ROOT,
                    capture_output=True,
                    check=True,
                    timeout=60,
                )
                .stdout.decode()
                .strip()
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RecoveryError("Build da imagem anterior falhou.") from exc
    require(image_id.startswith("sha256:"), "Imagem anterior sem identidade imutável.")
    return {"revision": full_revision, "image": IMAGE, "image_id": image_id}


if __name__ == "__main__":
    try:
        print(json.dumps(build(), sort_keys=True))
    except RecoveryError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None
