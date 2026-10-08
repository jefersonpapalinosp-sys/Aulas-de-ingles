"""Armazenamento local privado das gravações de speaking."""

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
        if not key or Path(key).name != key:
            raise ValueError("Chave de áudio inválida.")
        return self.root / key

    def save(self, data: bytes, mime_type: str) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        key = f"{uuid4().hex}{MIME_EXTENSIONS[mime_type]}"
        destination = self._path(key)
        temporary = destination.with_suffix(f"{destination.suffix}.tmp")
        temporary.write_bytes(data)
        temporary.replace(destination)
        return key

    def path(self, key: str) -> Path | None:
        path = self._path(key)
        return path if path.is_file() else None

    def delete(self, key: str | None) -> None:
        if key:
            self._path(key).unlink(missing_ok=True)
