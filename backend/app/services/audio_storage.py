"""Armazenamento local privado das gravações de speaking."""

import hashlib
import os
import stat
from pathlib import Path
from uuid import uuid4

MIME_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}


def normalized_mime_type(value: str | None) -> str | None:
    """Remove parâmetros de codec e aceita somente formatos de áudio conhecidos."""
    if not value:
        return None
    mime_type = value.split(";", 1)[0].strip().lower()
    return mime_type if mime_type in MIME_EXTENSIONS else None


class AudioStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        # A chave é gerada por este serviço, mas a validação também protege
        # leituras de registros antigos ou alterados diretamente no banco.
        if not key or Path(key).name != key or key in {".", ".."}:
            raise ValueError("Chave de áudio inválida.")
        return self.root / key

    def save(self, data: bytes, mime_type: str) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        key = f"{uuid4().hex}{MIME_EXTENSIONS[mime_type]}"
        destination = self._path(key)
        temporary = destination.with_suffix(f"{destination.suffix}.tmp")
        try:
            with temporary.open("xb") as stream:
                temporary.chmod(0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(destination)
            # Publicar no SQL somente após persistir bytes e entrada de diretório.
            # Se o fsync falhar, preservar eventual órfão para reconciliação.
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return key

    def matches(self, key: str | None, data: bytes) -> bool:
        """Retry de PUT: comparar sem carregar um arquivo legado arbitrário em memória."""
        if not key:
            return False
        try:
            existing = self.read_verified(key, None, len(data))
        except (OSError, ValueError):
            return False
        return existing == data

    def read_verified(self, key: str, digest: str | None, limit: int) -> bytes:
        """Leitura limitada sem seguir symlink; valida baseline quando disponível."""
        path = self._path(key)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or not 0 < before.st_size <= limit
            ):
                raise ValueError("audio_unsafe")
            parts = bytearray()
            while len(parts) <= limit:
                chunk = os.read(descriptor, min(65_536, limit + 1 - len(parts)))
                if not chunk:
                    break
                parts.extend(chunk)
            after = os.fstat(descriptor)
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ) or len(parts) != before.st_size:
                raise ValueError("audio_changed")
            if digest is not None and hashlib.sha256(parts).hexdigest() != digest:
                raise ValueError("audio_checksum_mismatch")
            return bytes(parts)
        finally:
            os.close(descriptor)

    def path(self, key: str) -> Path | None:
        path = self._path(key)
        return path if not path.is_symlink() and path.is_file() else None

    def delete(self, key: str | None) -> None:
        if key:
            self._path(key).unlink(missing_ok=True)
