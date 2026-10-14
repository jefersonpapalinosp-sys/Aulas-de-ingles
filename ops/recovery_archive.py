"""Formato de backup conjunto, sem dependência de Docker ou banco nos testes."""

import hashlib
import json
import os
import re
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

FORMAT = "aulas-recovery-v1"
ARTIFACTS = ("database.dump", "voice.tar")
MAX_AUDIO = 64 * 1024 * 1024
MAX_FILES = 100_000
MAX_TOTAL = 20 * 1024 * 1024 * 1024


class RecoveryError(RuntimeError):
    """Erro operacional seguro para exibir, sem corpos, credenciais ou SQL."""


def require(condition, message):
    if not condition:
        raise RecoveryError(message)


def safe_key(key):
    require(
        isinstance(key, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", key)
        and not key.endswith(".tmp"),
        "Chave de áudio insegura ou upload incompleto.",
    )


def digest(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.hexdigest()


def file_info(path):
    require(
        path.is_file() and not path.is_symlink(),
        "Artefato ausente ou link não permitido.",
    )
    with path.open("rb") as stream:
        return {"size": path.stat().st_size, "sha256": digest(stream)}


def audio_inventory(path):
    """Não extrai nada. Links, traversal, duplicatas e arquivos especiais são recusados."""
    inventory = {}
    total = 0
    try:
        with tarfile.open(path, "r:") as archive:
            for member in archive:
                safe_key(member.name)
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
                with archive.extractfile(member) as stream:
                    inventory[member.name] = {
                        "size": member.size,
                        "sha256": digest(stream),
                    }
    except (tarfile.TarError, OSError) as exc:
        raise RecoveryError("Arquivo de voz inválido ou truncado.") from exc
    return inventory


def check_references(snapshot, inventory):
    require(
        isinstance(snapshot, dict) and bool(snapshot.get("revision")),
        "Snapshot sem revisão de schema.",
    )
    require(
        isinstance(snapshot.get("counts"), dict) and isinstance(snapshot.get("audio"), list),
        "Snapshot incompleto.",
    )
    keys = set()
    for reference in snapshot["audio"]:
        require(isinstance(reference, dict), "Referência de áudio inválida.")
        key = reference.get("key")
        if key is None:
            require(reference.get("status") != "ready", "Áudio pronto sem chave no banco.")
            continue
        safe_key(key)
        require(key not in keys, "Chave de áudio referenciada mais de uma vez.")
        keys.add(key)
        require(
            key in inventory and inventory[key]["size"] == reference.get("size"),
            "Referência de áudio ausente ou tamanho divergente.",
        )
    # Órfãos são conservados no pacote, não apagados nem escondidos.
    return len(inventory.keys() - keys)


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def verify_bundle(path):
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
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        require(
            manifest["format"] == FORMAT and manifest["bundle_id"] == path.name,
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
        orphans = check_references(manifest["snapshot"], inventory)
        require(
            manifest["unreferenced_audio_count"] == orphans,
            "Contagem de áudios sem referência divergente.",
        )
        return manifest
    except (KeyError, TypeError, ValueError) as exc:
        raise RecoveryError("Manifesto inválido ou incompleto.") from exc


def create_bundle(root, capture):
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
