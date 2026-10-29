"""Formato de backup conjunto, sem dependência de Docker ou banco nos testes."""

import hashlib
import json
import os
import re
import tarfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, TypedDict
from uuid import uuid4

FORMAT = "aulas-recovery-v2"
LEGACY_FORMAT = "aulas-recovery-v1"
ARTIFACTS = ("database.dump", "voice.tar")
MAX_AUDIO = 64 * 1024 * 1024
MAX_FILES = 100_000
MAX_TOTAL = 20 * 1024 * 1024 * 1024


class FileInfo(TypedDict):
    size: int
    sha256: str


class RecoveryError(RuntimeError):
    """Erro operacional seguro para exibir, sem corpos, credenciais ou SQL."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise RecoveryError(message)


def safe_key(key: object) -> str:
    if (
        not isinstance(key, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", key)
        or key.endswith(".tmp")
    ):
        raise RecoveryError("Chave de áudio insegura ou upload incompleto.")
    return key


def safe_storage_member(name: object) -> None:
    """Somente voz plana ou três nomes reservados de uma operação de quarentena."""
    if isinstance(name, str) and name.startswith(".quarantine/"):
        require(
            re.fullmatch(r"\.quarantine/[a-f0-9]{32}/(?:audio|record\.json|restore\.json)", name),
            "Caminho de quarentena inseguro.",
        )
    else:
        safe_key(name)


def digest(stream: IO[bytes]) -> str:
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.hexdigest()


def file_info(path: Path) -> FileInfo:
    require(
        path.is_file() and not path.is_symlink(),
        "Artefato ausente ou link não permitido.",
    )
    with path.open("rb") as stream:
        return {"size": path.stat().st_size, "sha256": digest(stream)}


def audio_inventory(path: Path) -> dict[str, FileInfo]:
    """Não extrai nada. Links, traversal, duplicatas e arquivos especiais são recusados."""
    inventory: dict[str, FileInfo] = {}
    total = 0
    try:
        with tarfile.open(path, "r:") as archive:
            for member in archive:
                safe_storage_member(member.name)
                require(
                    member.isfile() and member.name not in inventory,
                    "Áudio duplicado, link ou arquivo especial no pacote.",
                )
                require(
                    0 < member.size <= MAX_AUDIO,
                    "Tamanho de áudio fora do limite operacional.",
                )
                total += member.size
                require(
                    len(inventory) < MAX_FILES and total <= MAX_TOTAL,
                    "Pacote excede limites operacionais; não foi extraído.",
                )
                source = archive.extractfile(member)
                if source is None:
                    raise RecoveryError("Entrada de voz sem conteúdo regular.")
                with source as stream:
                    inventory[member.name] = {
                        "size": member.size,
                        "sha256": digest(stream),
                    }
    except (tarfile.TarError, OSError) as exc:
        raise RecoveryError("Arquivo de voz inválido ou truncado.") from exc
    return inventory


def check_references(snapshot: object, inventory: Mapping[str, FileInfo]) -> int:
    if not isinstance(snapshot, dict) or not snapshot.get("revision"):
        raise RecoveryError("Snapshot sem revisão de schema.")
    audio = snapshot.get("audio")
    if not isinstance(snapshot.get("counts"), dict) or not isinstance(audio, list):
        raise RecoveryError("Snapshot incompleto.")
    keys: set[str] = set()
    for reference in audio:
        if not isinstance(reference, dict):
            raise RecoveryError("Referência de áudio inválida.")
        key = reference.get("key")
        if key is None:
            require(reference.get("status") != "ready", "Áudio pronto sem chave no banco.")
            continue
        key = safe_key(key)
        require(key not in keys, "Chave de áudio referenciada mais de uma vez.")
        keys.add(key)
        require(
            key in inventory and inventory[key]["size"] == reference.get("size"),
            "Referência de áudio ausente ou tamanho divergente.",
        )
    # Órfãos são conservados no pacote, não apagados nem escondidos.
    return len({key for key in inventory if not key.startswith(".quarantine/")} - keys)


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def verify_bundle(path: str | Path) -> dict[str, object]:
    path = Path(path)
    require(
        path.is_dir() and not path.is_symlink() and not path.name.startswith(".partial-"),
        "Use um pacote publicado, não um diretório parcial ou link.",
    )
    require(
        {p.name for p in path.iterdir()} == {*ARTIFACTS, "manifest.json"},
        "Pacote incompleto ou com arquivos inesperados.",
    )
    manifest_file = path / "manifest.json"
    require(
        not manifest_file.is_symlink() and manifest_file.stat().st_size < 32 * 1024 * 1024,
        "Manifesto inválido.",
    )
    try:
        manifest: object = json.loads(manifest_file.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("artifacts"), dict):
            raise RecoveryError("Manifesto inválido ou incompleto.")
        require(
            manifest["format"] in {FORMAT, LEGACY_FORMAT} and manifest["bundle_id"] == path.name,
            "Formato ou identidade do pacote divergente.",
        )
        require(set(manifest["artifacts"]) == set(ARTIFACTS), "Manifesto incompleto.")
        for name in ARTIFACTS:
            actual = file_info(path / name)
            require(
                actual == manifest["artifacts"][name] and actual["size"] > 0,
                "Checksum/tamanho divergente; restauração bloqueada.",
            )
        inventory = audio_inventory(path / "voice.tar")
        require(inventory == manifest["audio_files"], "Inventário de voz divergente.")
        quarantined = sum(name.startswith(".quarantine/") for name in inventory)
        if manifest["format"] == LEGACY_FORMAT:
            require(quarantined == 0, "Quarentena exige formato de backup v2.")
        else:
            require(
                manifest.get("quarantine_entry_count") == quarantined,
                "Contagem de entradas de quarentena divergente.",
            )
        orphans = check_references(manifest["snapshot"], inventory)
        require(
            manifest["unreferenced_audio_count"] == orphans,
            "Contagem de áudios sem referência divergente.",
        )
        return manifest
    except (KeyError, TypeError, ValueError) as exc:
        raise RecoveryError("Manifesto inválido ou incompleto.") from exc


def create_bundle(
    root: str | Path, capture: Callable[[Path], Mapping[str, object]]
) -> Path:
    """capture escreve os dois artefatos e retorna metadados após conferir quiescência.

    Em erro preserva .partial-* privado para diagnóstico. Nunca publica um parcial.
    A captura deve validar o pg_dump com pg_restore --list antes de retornar.
    """
    root = Path(root)
    require(
        not root.is_symlink() and not root.parent.is_symlink(),
        "Diretório de backups ou seu pai não pode ser link.",
    )
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(
        root.stat().st_mode & 0o077 == 0,
        "Diretório de backups deve ser privado (permissão 700); ajuste conscientemente.",
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    bundle_id = f"aulas-{stamp}-{uuid4().hex}"
    staging = root / f".partial-{bundle_id}"
    destination = root / bundle_id
    staging.mkdir(mode=0o700)
    metadata = capture(staging)
    artifacts = {name: file_info(staging / name) for name in ARTIFACTS}
    require(all(item["size"] > 0 for item in artifacts.values()), "Artefato vazio.")
    inventory = audio_inventory(staging / "voice.tar")
    orphans = check_references(metadata["snapshot"], inventory)
    manifest = {
        **metadata,
        "format": FORMAT,
        "bundle_id": bundle_id,
        "created_at": datetime.now(UTC).isoformat(),
        "artifacts": artifacts,
        "audio_files": inventory,
        "unreferenced_audio_count": orphans,
        "quarantine_entry_count": sum(name.startswith(".quarantine/") for name in inventory),
    }
    for name in ARTIFACTS:
        os.chmod(staging / name, 0o600)
        with (staging / name).open("rb") as stream:
            os.fsync(stream.fileno())
    write_json(staging / "manifest.json", manifest)
    require(not destination.exists(), "Colisão de pacote; nada foi sobrescrito.")
    staging.rename(destination)  # Publicação no mesmo filesystem, só após captura/validação.
    with_directory = os.open(root, os.O_RDONLY)
    try:
        os.fsync(with_directory)
    finally:
        os.close(with_directory)
    return destination
