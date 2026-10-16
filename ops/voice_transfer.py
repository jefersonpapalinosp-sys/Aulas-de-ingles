"""Executado em container sem rede. Exporta em RO; importa apenas em volume vazio."""

import os
import sys
import tarfile
from pathlib import Path

from recovery_archive import (
    MAX_AUDIO,
    MAX_FILES,
    MAX_TOTAL,
    require,
    safe_storage_member,
)

ROOT = Path("/voice")


def bounded_entries(directory, limit=MAX_FILES):
    entries = []
    for entry in directory.iterdir():
        require(len(entries) < limit, "Muitas entradas no diretório de voz/quarentena.")
        entries.append(entry)
    return sorted(entries)


def export_voice():
    # Valida toda a árvore antes de emitir o tar. Não segue symlinks.
    files = []
    for path in bounded_entries(ROOT):
        if path.name == ".quarantine":
            require(
                path.is_dir() and not path.is_symlink(), "Quarentena não pode ser link."
            )
            operations = bounded_entries(path)
            # O pré-check de restore usa inventário vazio para admitir o destino.
            # Não ocultar diretório parcial vazio como se fosse storage vazio.
            require(bool(operations), "Quarentena parcial vazia exige revisão manual.")
            for operation in operations:
                # Checar formato antes de percorrer mais um nível.
                safe_storage_member(f".quarantine/{operation.name}/record.json")
                require(
                    operation.is_dir() and not operation.is_symlink(),
                    "Operação de quarentena insegura.",
                )
                entries = bounded_entries(operation, limit=3)
                require(bool(entries), "Journal ausente: preservar operação parcial.")
                files.extend(entries)
                require(len(files) <= MAX_FILES, "Muitas entradas de voz/quarentena.")
        else:
            files.append(path)
    require(len(files) <= MAX_FILES, "Muitos arquivos de voz.")
    total = 0
    for path in files:
        safe_storage_member(path.relative_to(ROOT).as_posix())
        require(
            path.is_file() and not path.is_symlink(),
            "Storage contém link/diretório inesperado.",
        )
        size = path.stat().st_size
        require(0 < size <= MAX_AUDIO, "Áudio vazio ou grande demais.")
        total += size
    require(total <= MAX_TOTAL, "Storage excede limite operacional.")
    # Interrupção entre link e unlink pode deixar dois nomes: copiar ambos como bytes,
    # não exportar hardlink que o importador seguro recusaria.
    with tarfile.open(
        fileobj=sys.stdout.buffer, mode="w|", dereference=True
    ) as archive:
        for path in files:
            archive.add(
                path, arcname=path.relative_to(ROOT).as_posix(), recursive=False
            )


def import_voice():
    require(not any(ROOT.iterdir()), "Destino de voz não está vazio.")
    seen = set()
    total = 0
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|") as archive:
        for member in archive:
            safe_storage_member(member.name)
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
            destination = ROOT / member.name
            if member.name.startswith(".quarantine/"):
                for parent in (ROOT / ".quarantine", destination.parent):
                    parent.mkdir(mode=0o700, exist_ok=True)
                    require(
                        parent.is_dir() and not parent.is_symlink(),
                        "Diretório inseguro.",
                    )
                    os.chown(parent, 10001, 10001)
            with (
                archive.extractfile(member) as source,
                destination.open("xb") as target,
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
    except Exception:  # noqa: BLE001 - fronteira CLI sanitiza falhas sem expor dados privados.
        print(
            "Transferência de voz recusada; destino parcial deve ser preservado.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
