"""Executado em container sem rede. Exporta em RO; importa apenas em volume vazio."""

import os
import sys
import tarfile
from pathlib import Path

from recovery_archive import MAX_AUDIO, MAX_FILES, MAX_TOTAL, require, safe_key

ROOT = Path("/voice")


def export_voice():
    # Valida toda a árvore antes de emitir o tar. Não segue symlinks.
    files = sorted(ROOT.iterdir())
    require(len(files) <= MAX_FILES, "Muitos arquivos de voz.")
    total = 0
    for path in files:
        safe_key(path.name)
        require(
            path.is_file() and not path.is_symlink(),
            "Storage contém link/diretório inesperado.",
        )
        size = path.stat().st_size
        require(0 < size <= MAX_AUDIO, "Áudio vazio ou grande demais.")
        total += size
    require(total <= MAX_TOTAL, "Storage excede limite operacional.")
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as archive:
        for path in files:
            archive.add(path, arcname=path.name, recursive=False)


def import_voice():
    require(not any(ROOT.iterdir()), "Destino de voz não está vazio.")
    seen = set()
    total = 0
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|") as archive:
        for member in archive:
            safe_key(member.name)
            require(
                member.isfile() and member.name not in seen,
                "Tipo ou nome de áudio inseguro.",
            )
            require(0 < member.size <= MAX_AUDIO, "Tamanho de áudio inválido.")
            seen.add(member.name)
            total += member.size
            require(
                len(seen) <= MAX_FILES and total <= MAX_TOTAL,
                "Limite operacional excedido.",
            )
            # Não usa extract/extractall e não herda permissões, donos ou caminhos do tar.
            with (
                archive.extractfile(member) as source,
                (ROOT / member.name).open("xb") as target,
            ):
                os.chmod(target.name, 0o600)
                remaining = member.size
                while remaining:
                    chunk = source.read(min(remaining, 1024 * 1024))
                    require(bool(chunk), "Áudio truncado.")
                    target.write(chunk)
                    remaining -= len(chunk)
                target.flush()
                os.fsync(target.fileno())
                os.chown(target.name, 10001, 10001)
    os.chown(ROOT, 10001, 10001)
    os.chmod(ROOT, 0o700)


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["export"]:
            export_voice()
        elif sys.argv[1:] == ["import"]:
            import_voice()
        else:
            raise ValueError("ação inválida")
    except Exception:
        print(
            "Transferência de voz recusada; destino parcial deve ser preservado.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
