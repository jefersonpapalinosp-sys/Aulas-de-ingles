"""Quarentena local reversível, uma chave por operação, sem expurgo.

Chamador deve manter LOCK TABLE speaking_attempt IN EXCLUSIVE MODE e revalidar
referências. flock serializa operadores no mesmo volume, não substitui esse lock SQL.
O journal é durável antes da movimentação; link/fsync/unlink evita sobrescrita e
mantém ao menos um nome recuperável após interrupção do processo.
"""

import fcntl
import hashlib
import json
import os
import re
import stat
import time
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from app.services.audio_audit import KEY, MIN_AGE_SECONDS
from app.services.audio_upload import MAX_AUDIO_BYTES

OPERATION = re.compile(r"[a-f0-9]{32}")
DIGEST = re.compile(r"[a-f0-9]{64}")
DIRECTORY = ".quarantine"


class QuarantineRefused(RuntimeError):
    """Somente códigos estáveis, sem paths, SQL ou dados pessoais na mensagem."""


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _directory(parent: int, name: str, *, create: bool = False) -> int:
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
    result = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    info = os.fstat(result)
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        os.close(result)
        raise QuarantineRefused("unsafe_quarantine_directory")
    return result


class Quarantine:
    def __init__(self, root: Path, database: str) -> None:
        self.root = root
        self.database = database
        self.fd = -1
        self.deadline = 0.0

    def __enter__(self) -> "Quarantine":
        if (
            not self.root.is_absolute()
            or len(self.root.parts) < 3
            or self.root == Path.home()
            or self.root.resolve(strict=True) != self.root
        ):
            raise QuarantineRefused("unsafe_storage_root")
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(self.fd)
            if info.st_mode & 0o022 or info.st_uid != os.geteuid():
                raise QuarantineRefused("unsafe_storage_permissions")
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.fd)
            self.fd = -1
            raise
        self.deadline = time.monotonic() + 5
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        os.close(self.fd)
        self.fd = -1

    def _budget(self) -> None:
        if time.monotonic() >= self.deadline:
            raise QuarantineRefused("filesystem_budget")

    def _file(self, directory: int, name: str) -> tuple[os.stat_result, str] | None:
        self._budget()
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink not in (1, 2)
                or not 0 < before.st_size <= MAX_AUDIO_BYTES
                or before.st_uid != os.geteuid()
                or before.st_mode & 0o077
            ):
                raise QuarantineRefused("unsafe_audio_file")
            digest = hashlib.sha256()
            remaining = before.st_size
            while remaining:
                self._budget()
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    raise QuarantineRefused("changed_audio_file")
                digest.update(chunk)
                remaining -= len(chunk)
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if _identity(before) != _identity(after) or _identity(after) != _identity(named):
                raise QuarantineRefused("changed_audio_file")
            # Inclui arquivos legados: persistir bytes antes do journal/movimentação.
            os.fsync(fd)
            return after, digest.hexdigest()
        finally:
            os.close(fd)

    def _write(self, directory: int, name: str, record: dict[str, Any]) -> None:
        # Arquivo parcial não é interpretado como journal válido nem reparado por suposição.
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(json.dumps(record, sort_keys=True).encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)

    def _read(self, directory: int, name: str) -> dict[str, Any]:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or not 0 < info.st_size <= 4096
                or info.st_mode & 0o077
                or info.st_uid != os.geteuid()
            ):
                raise QuarantineRefused("unsafe_journal")
            data = os.read(fd, 4097)
            result = json.loads(data)
            if not isinstance(result, dict):
                raise QuarantineRefused("invalid_journal")
            return result
        finally:
            os.close(fd)

    def prepare(self, key: str, digest: str, operation: str, now: datetime) -> dict[str, Any]:
        if (
            not KEY.fullmatch(key)
            or not DIGEST.fullmatch(digest)
            or not OPERATION.fullmatch(operation)
        ):
            raise QuarantineRefused("invalid_target")
        source = self._file(self.fd, key)
        if source is None:
            raise QuarantineRefused("source_missing")
        info, observed = source
        if info.st_nlink != 1 or observed != digest:
            raise QuarantineRefused("checksum_or_links_changed")
        if now.timestamp() - max(info.st_mtime, info.st_ctime) < MIN_AGE_SECONDS:
            raise QuarantineRefused("recent_file_protected")
        record = {
            "version": 1,
            "operation": operation,
            "key": key,
            "sha256": digest,
            "size": info.st_size,
            "inode": info.st_ino,
            "device": info.st_dev,
            "database": self.database,
            "created_at": now.isoformat(),
            "source_mtime_ns": info.st_mtime_ns,
            "source_ctime_ns": info.st_ctime_ns,
            "root_inode": os.fstat(self.fd).st_ino,
        }
        parent = _directory(self.fd, DIRECTORY, create=True)
        try:
            # Operação fornecida pelo operador ANTES da ação, nunca gerar silenciosamente
            # outra operação quando a resposta anterior tiver sido perdida.
            os.mkdir(operation, 0o700, dir_fd=parent)
            os.fsync(parent)
            target = _directory(parent, operation)
            try:
                self._write(target, "record.json", record)
            finally:
                os.close(target)
        finally:
            os.close(parent)
        return record

    def load(self, operation: str) -> dict[str, Any]:
        if not OPERATION.fullmatch(operation):
            raise QuarantineRefused("invalid_operation")
        parent = _directory(self.fd, DIRECTORY)
        try:
            target = _directory(parent, operation)
            try:
                record = self._read(target, "record.json")
            finally:
                os.close(target)
        finally:
            os.close(parent)
        if (
            record.get("version") != 1
            or record.get("operation") != operation
            or record.get("database") != self.database
            or record.get("root_inode") != os.fstat(self.fd).st_ino
            or not isinstance(record.get("key"), str)
            or not KEY.fullmatch(record["key"])
            or not isinstance(record.get("sha256"), str)
            or not DIGEST.fullmatch(record["sha256"])
        ):
            raise QuarantineRefused("journal_target_mismatch")
        return record

    def finish(self, record: dict[str, Any], *, restore: bool = False) -> dict[str, Any]:
        """Chamador revalida referência SQL, inclusive ao retomar uma operação antiga."""
        parent = _directory(self.fd, DIRECTORY)
        try:
            target = _directory(parent, record["operation"])
            try:
                return self._finish(target, record, restore=restore)
            finally:
                os.close(target)
        finally:
            os.close(parent)

    def _finish(self, target: int, record: dict[str, Any], *, restore: bool) -> dict[str, Any]:
        try:
            marker = self._read(target, "restore.json")
        except FileNotFoundError:
            marker = None
        if marker is not None:
            if marker != {"operation": record["operation"], "intent": "restore"}:
                raise QuarantineRefused("invalid_restore_journal")
            restore = True
        source = self._file(self.fd, record["key"])
        saved = self._file(target, "audio")
        present = [item for item in (source, saved) if item is not None]
        if not present:
            raise QuarantineRefused("audio_missing_manual_review")
        for info, digest in present:
            if (
                digest != record["sha256"]
                or info.st_size != record["size"]
                or info.st_ino != record["inode"]
                or info.st_dev != record["device"]
                or info.st_mtime_ns != record["source_mtime_ns"]
                or info.st_nlink != len(present)
            ):
                raise QuarantineRefused("audio_conflict_manual_review")
        # Antes do primeiro link, um ctime novo invalida a seleção original.
        if (
            not restore
            and source
            and not saved
            and source[0].st_ctime_ns != record["source_ctime_ns"]
        ):
            raise QuarantineRefused("changed_after_prepare")
        if restore and marker is None:
            self._write(
                target, "restore.json", {"operation": record["operation"], "intent": "restore"}
            )
        origin, destination = (target, self.fd) if restore else (self.fd, target)
        old_name, new_name = ("audio", record["key"]) if restore else (record["key"], "audio")
        old, new = (saved, source) if restore else (source, saved)
        self._budget()
        if old:
            if _identity(os.stat(old_name, dir_fd=origin, follow_symlinks=False)) != _identity(
                old[0]
            ):
                raise QuarantineRefused("changed_during_move")
            if not new:
                os.link(
                    old_name,
                    new_name,
                    src_dir_fd=origin,
                    dst_dir_fd=destination,
                    follow_symlinks=False,
                )
            # Confirmar as duas entradas e persistir destino ANTES de remover a origem.
            checked = self._file(destination, new_name)
            if checked is None or checked[1] != record["sha256"]:
                raise QuarantineRefused("changed_during_move")
            new_info = checked[0]
            old_info = os.stat(old_name, dir_fd=origin, follow_symlinks=False)
            if (
                not stat.S_ISREG(old_info.st_mode)
                or _identity(old_info) != _identity(new_info)
                or old_info.st_ino != record["inode"]
                or old_info.st_nlink != 2
                or old_info.st_size != record["size"]
                or old_info.st_mtime_ns != record["source_mtime_ns"]
            ):
                raise QuarantineRefused("changed_during_move")
            os.fsync(destination)
            os.unlink(old_name, dir_fd=origin)
            os.fsync(origin)
        return {
            "version": 1,
            "operation": record["operation"],
            "key": record["key"],
            "state": "restored" if restore else "quarantined",
            "sha256": record["sha256"],
            "size": record["size"],
            "deleted": False,
        }
