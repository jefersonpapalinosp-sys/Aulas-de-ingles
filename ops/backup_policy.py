"""Holds externos ao pacote e retenção de cópias cifradas, sempre com prévia."""

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

from ops.recovery_archive import FileInfo, file_info, require, write_json
from ops.recovery_prune import BUNDLE_RE, Bundle, parse_stamp, select


def held(root: Path, name: str) -> bool:
    directory = root / ".holds"
    # Um marcador malformado nunca autoriza apagar um backup.
    return directory.is_symlink() or os.path.lexists(directory / name)


def hold(root: Path, name: str, *, release: bool = False) -> None:
    require(BUNDLE_RE.fullmatch(name), "Identidade de backup inválida.")
    require(root.is_dir() and not root.is_symlink(), "Diretório de backups inválido.")
    directory = root / ".holds"
    require(not directory.is_symlink(), "Diretório de holds não pode ser link.")
    directory.mkdir(mode=0o700, exist_ok=True)
    marker = directory / name
    require(not marker.is_symlink(), "Marcador não pode ser link.")
    if release:
        require(marker.is_file(), "Hold ausente.")
        marker.unlink()
    elif not marker.exists():
        write_json(marker, {"bundle_id": name, "hold": True})


class EncryptedPlan(TypedDict):
    keep: list[str]
    remove: dict[str, FileInfo]


def record_copy(path: Path, info: FileInfo) -> None:
    name = path.name.removesuffix(".tar.age")
    if not BUNDLE_RE.fullmatch(name):
        return
    directory = path.parent / ".verified"
    require(not directory.is_symlink(), "Diretório de recibos cifrados não pode ser link.")
    directory.mkdir(mode=0o700, exist_ok=True)
    write_json(directory / f"{name}.json", {"bundle_id": name, **info})


def encrypted_plan(root: Path) -> EncryptedPlan:
    require(root.is_dir() and not root.is_symlink(), "Diretório cifrado inválido.")
    bundles = []
    hashes = {}
    for path in root.iterdir():
        name = path.name.removesuffix(".tar.age")
        match = BUNDLE_RE.fullmatch(name)
        if not path.name.endswith(".tar.age") or not match or path.is_symlink():
            continue
        stamp = parse_stamp(match["stamp"])
        if stamp is None or not path.is_file():
            continue
        info = file_info(path)
        require(info["size"] > 0, "Cópia cifrada vazia; poda recusada.")
        certificate = root / ".verified" / f"{name}.json"
        if (
            certificate.parent.is_symlink()
            or certificate.is_symlink()
            or not certificate.is_file()
            or certificate.stat().st_size > 4096
        ):
            continue
        try:
            verified = json.loads(certificate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if verified != {"bundle_id": name, **info}:
            continue
        bundles.append(Bundle(name, stamp, info["size"]))
        hashes[name] = info
    require(bundles, "Nenhuma cópia cifrada reconhecida; poda recusada.")
    keep, remove = select(bundles)
    protected = [b.name for b in remove if held(root, b.name)]
    return {
        "keep": [b.name for b, _ in keep] + protected,
        "remove": {b.name: hashes[b.name] for b in remove if b.name not in protected},
    }


def prune_encrypted(root: Path, *, apply: bool = False) -> dict[str, object]:
    plan = encrypted_plan(root)
    if apply:
        # Recalcular antes de cada remoção protege um hold criado após a prévia.
        for name, expected in plan["remove"].items():
            current = encrypted_plan(root)
            require(name in current["remove"], "Plano mudou; refaça a prévia.")
            path = root / f"{name}.tar.age"
            require(file_info(path) == expected and not held(root, name), "Cópia mudou.")
            path.unlink()
    return {**plan, "applied": apply}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    mark = commands.add_parser("hold")
    mark.add_argument("root", type=Path)
    mark.add_argument("bundle_id")
    mark.add_argument("--release", action="store_true")
    mark.add_argument("--confirm")
    prune = commands.add_parser("prune-encrypted")
    prune.add_argument("root", type=Path)
    prune.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "hold":
            require(
                not args.release or args.confirm == args.bundle_id,
                "Remover hold exige confirmar o identificador.",
            )
            hold(args.root, args.bundle_id, release=args.release)
            print("Hold atualizado.")
        else:
            print(json.dumps(prune_encrypted(args.root, apply=args.apply), indent=2))
        return 0
    except Exception as exc:
        from ops.diagnostics import diagnostic

        diagnostic("backup_policy", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
