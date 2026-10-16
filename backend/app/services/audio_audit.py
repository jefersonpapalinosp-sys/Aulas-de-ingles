"""Inventário limitado, somente leitura. Candidatos NÃO autorizam exclusão futura."""

import hashlib
import os
import re
import stat
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

KEY = re.compile(r"[a-f0-9]{32}\.(?:webm|ogg|m4a|mp3|wav)")
MAX_ROWS = 10_000
MAX_HASH_BYTES = 100 * 1024**2
MIN_AGE_SECONDS = 24 * 3600


@dataclass(frozen=True)
class AudioReference:
    id: int
    status: str
    key: str | None
    size: int | None
    created_at: datetime
    digest: str | None = None


def inventory(
    root: Path,
    references: list[AudioReference],
    now: datetime,
    *,
    snapshot_complete: bool = True,
    min_age: int = MIN_AGE_SECONDS,
    max_files: int = MAX_ROWS,
    max_hash_bytes: int = MAX_HASH_BYTES,
    max_seconds: float = 30,
) -> dict[str, Any]:
    if min_age < MIN_AGE_SECONDS or not 1 <= max_files <= MAX_ROWS:
        raise ValueError("Período mínimo de 24 h; limite de 1 a 10000 arquivos.")
    findings: list[dict[str, Any]] = []
    complete = snapshot_complete
    deadline = time.monotonic() + max_seconds
    budget = max_hash_bytes
    by_key = {item.key: item for item in references if item.key}
    seen: set[str] = set()

    def add(kind: str, **fields: Any) -> None:
        findings.append({"kind": kind, **fields})

    def report() -> dict[str, Any]:
        return {
            "version": 1,
            "dry_run": True,
            "complete": complete,
            "generated_at": now.isoformat(),
            "min_age_seconds": min_age,
            "references_scanned": len(references),
            "files_scanned": len(seen),
            "bytes_hashed": max_hash_bytes - budget,
            "counts": dict(Counter(item["kind"] for item in findings)),
            "findings": findings,
            "warning": "Snapshot observacional; não autoriza apagar ou mover arquivos.",
        }

    for item in references:
        if item.status == "pending" and (now - item.created_at).total_seconds() >= min_age:
            add("pending_old", attempt_id=item.id)
        if item.status == "ready" and not item.key:
            add("ready_without_key", attempt_id=item.id)
        if item.key and (Path(item.key).name != item.key or item.key in {".", ".."}):
            add("invalid_reference", attempt_id=item.id)

    # Recusa raiz ampla, redirecionada ou ausente. Nunca cria a pasta para "corrigir".
    try:
        if (
            not root.is_absolute()
            or len(root.parts) < 3
            or root.resolve(strict=True) != root
            or root == Path.home()
        ):
            raise ValueError("unsafe root")
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (OSError, ValueError):
        complete = False
        add("storage_unavailable")
        return report()
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if len(seen) >= max_files or time.monotonic() >= deadline:
                    complete = False
                    add("scan_limit")
                    break
                name = entry.name
                seen.add(name)
                reference = by_key.get(name)
                try:
                    info = entry.stat(follow_symlinks=False)
                    if (
                        name == ".quarantine"
                        and stat.S_ISDIR(info.st_mode)
                        and info.st_uid == os.geteuid()
                        and not info.st_mode & 0o077
                    ):
                        add("quarantine_directory_protected", key=name)
                        continue  # Não recursa nem interpreta journals neste inventário.
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        add("unsafe_entry", key=name)
                        continue
                    if name.endswith(".tmp"):
                        add("temporary_protected", key=name)
                        continue
                    if reference and reference.size is not None and reference.size != info.st_size:
                        add("size_mismatch", key=name, attempt_id=reference.id)
                    # ctime protege arquivo novo/copied mesmo com mtime retrodatado.
                    if now.timestamp() - max(info.st_mtime, info.st_ctime) < min_age:
                        add("recent_protected", key=name)
                        continue
                    if not reference and (not KEY.fullmatch(name) or not snapshot_complete):
                        add("unclassified_protected", key=name)
                        continue
                    if info.st_size > budget:
                        complete = False
                        add("hash_budget", key=name)
                        continue
                    descriptor = os.open(
                        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
                    )
                    try:
                        before = os.fstat(descriptor)
                        if (
                            not stat.S_ISREG(before.st_mode)
                            or before.st_nlink != 1
                            or before.st_ino != info.st_ino
                            or before.st_size != info.st_size
                            or before.st_mtime_ns != info.st_mtime_ns
                            or before.st_ctime_ns != info.st_ctime_ns
                        ):
                            complete = False
                            add("changed_protected", key=name)
                            continue
                        digest = hashlib.sha256()
                        remaining = info.st_size
                        while remaining and time.monotonic() < deadline:
                            chunk = os.read(descriptor, min(65536, remaining))
                            if not chunk:
                                break
                            digest.update(chunk)
                            remaining -= len(chunk)
                            budget -= len(chunk)
                        after = os.fstat(descriptor)
                        current = os.stat(name, dir_fd=directory, follow_symlinks=False)

                        def identity(s: os.stat_result) -> tuple[int, int, int, int]:
                            return s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns

                        if (
                            remaining
                            or identity(before) != identity(after)
                            or identity(after) != identity(current)
                        ):
                            complete = False
                            add("changed_protected", key=name)
                            continue
                    finally:
                        os.close(descriptor)
                    add(
                        "referenced" if reference else "orphan_candidate",
                        key=name,
                        sha256=digest.hexdigest(),
                        size=info.st_size,
                        baseline_verified=bool(
                            reference and reference.digest == digest.hexdigest()
                        ),
                    )
                    if reference and reference.digest and reference.digest != digest.hexdigest():
                        add("checksum_mismatch", key=name, attempt_id=reference.id)
                except OSError:
                    complete = False
                    add("unreadable_protected", key=name)
        if complete:
            for key, reference in by_key.items():
                if key not in seen and Path(key).name == key and key not in {".", ".."}:
                    add("missing_file", key=key, attempt_id=reference.id)
    finally:
        os.close(directory)
    return report()
