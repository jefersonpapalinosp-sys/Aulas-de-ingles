"""Gera e valida a configuração privada do deploy no EasyPanel.

O módulo nunca imprime valores de configuração. O arquivo real permanece local,
com permissão 0600, e é ignorado pelo Git e pelo contexto de build do Docker.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra" / "easypanel" / ".env.example"
COMPOSE = ROOT / "infra" / "easypanel" / "compose.yml"
DEFAULT_ENV = ROOT / ".env.easypanel"
PENDING_ORIGIN = "https://configure-domain.invalid"

SECRET_KEYS = (
    "EASYPANEL_DB_ADMIN_PASSWORD",
    "EASYPANEL_MIGRATOR_PASSWORD",
    "EASYPANEL_RUNTIME_PASSWORD",
    "EASYPANEL_WORKER_PASSWORD",
    "EASYPANEL_BACKUP_PASSWORD",
    "EASYPANEL_JWT_SECRET",
    "EASYPANEL_OPERATIONS_TOKEN",
)


class ConfigurationError(ValueError):
    """A configuração não é segura para o perfil público."""


def parse_env(contents: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(contents.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(f"linha {line_number} não possui KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ConfigurationError(f"chave inválida na linha {line_number}")
        if key in values:
            raise ConfigurationError(f"chave duplicada: {key}")
        values[key] = value.strip()
    return values


def validate_origin(origin: str) -> None:
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError("EASYPANEL_PUBLIC_ORIGIN é inválida") from exc

    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(
            "EASYPANEL_PUBLIC_ORIGIN deve ser uma origem HTTPS, sem porta, caminho ou credenciais"
        )
    if (
        not hostname
        or hostname.endswith(".")
        or "." not in hostname
        or hostname == "localhost"
        or hostname.endswith((".invalid", ".local", ".localhost"))
    ):
        raise ConfigurationError("EASYPANEL_PUBLIC_ORIGIN deve usar um domínio público válido")
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ConfigurationError("EASYPANEL_PUBLIC_ORIGIN possui domínio inválido") from exc
    labels = ascii_hostname.split(".")
    if len(ascii_hostname) > 253 or any(
        not re.fullmatch(r"(?!-)[a-z0-9-]{1,63}(?<!-)", label) for label in labels
    ):
        raise ConfigurationError("EASYPANEL_PUBLIC_ORIGIN possui domínio inválido")


def validate_values(values: dict[str, str]) -> None:
    origin = values.get("EASYPANEL_PUBLIC_ORIGIN", "")
    validate_origin(origin)

    secret_values: list[str] = []
    for key in SECRET_KEYS:
        value = values.get(key, "")
        if "GENERATE_" in value or not re.fullmatch(r"[0-9a-fA-F]{64,}", value):
            raise ConfigurationError(
                f"{key} deve conter ao menos 32 bytes aleatórios em hexadecimal"
            )
        if len(value) % 2:
            raise ConfigurationError(f"{key} deve possuir número par de caracteres")
        secret_values.append(value.lower())

    if len(set(secret_values)) != len(secret_values):
        raise ConfigurationError("todos os segredos devem ser independentes")

    if values.get("EASYPANEL_ASSISTED_FEATURES_ENABLED", "").lower() != "false":
        raise ConfigurationError(
            "o primeiro deploy deve manter EASYPANEL_ASSISTED_FEATURES_ENABLED=false"
        )


def validate_private_file(path: Path) -> dict[str, str]:
    if path.is_symlink():
        raise ConfigurationError("o arquivo privado não pode ser um link simbólico")
    try:
        file_stat = path.stat()
    except FileNotFoundError as exc:
        raise ConfigurationError(
            f"arquivo ausente: {path}; execute o comando de geração primeiro"
        ) from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise ConfigurationError("a configuração deve ser um arquivo regular")
    if stat.S_IMODE(file_stat.st_mode) != 0o600:
        raise ConfigurationError("a configuração privada deve usar permissão 0600")
    values = parse_env(path.read_text(encoding="utf-8"))
    validate_values(values)
    return values


def render_environment(origin: str) -> str:
    secret_by_key = {key: secrets.token_hex(32) for key in SECRET_KEYS}
    rendered: list[str] = []
    for raw_line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("EASYPANEL_PUBLIC_ORIGIN="):
            rendered.append(f"EASYPANEL_PUBLIC_ORIGIN={origin}")
            continue
        key = raw_line.split("=", 1)[0]
        if key in secret_by_key:
            rendered.append(f"{key}={secret_by_key[key]}")
            continue
        rendered.append(raw_line)
    return "\n".join(rendered) + "\n"


def create_environment(path: Path, origin: str) -> None:
    if path.is_symlink() or path.exists():
        raise ConfigurationError(f"recusado sobrescrever arquivo existente: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if origin != PENDING_ORIGIN:
        validate_origin(origin)
    contents = render_environment(origin)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        raise


def run_compose_validation(env_file: Path) -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(COMPOSE),
            "config",
            "--quiet",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ConfigurationError(
            "o Docker Compose recusou a configuração; execute-o manualmente para diagnosticar"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="gera o arquivo privado uma única vez")
    init_parser.add_argument(
        "--origin",
        default=PENDING_ORIGIN,
        help="origem HTTPS pública exata; sem ela, o check ficará bloqueado",
    )
    init_parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)

    check_parser = subparsers.add_parser("check", help="valida segurança e Compose")
    check_parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    check_parser.add_argument("--skip-compose", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            create_environment(args.env_file.resolve(), args.origin)
            print(f"Configuração privada criada com permissão 0600: {args.env_file}")
            print("Os valores não foram exibidos. Guarde uma cópia segura fora do Git.")
            return 0

        env_file = args.env_file.resolve()
        validate_private_file(env_file)
        if not args.skip_compose:
            run_compose_validation(env_file)
        print("Configuração privada e contrato de Compose aprovados.")
        return 0
    except ConfigurationError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
