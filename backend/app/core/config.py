"""Configuração da aplicação, lida do ambiente."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variáveis de ambiente da API.

    Os defaults apontam para o compose local; em qualquer outro lugar
    o valor vem do ambiente (ver .env.example na raiz do repo).
    """

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "info"

    # Em dev o default serve; em prod a aplicação recusa subir sem valor próprio.
    # 32 bytes é o mínimo do RFC 7518 para HS256.
    jwt_secret: str = "dev-apenas-troque-isto-em-producao-32b"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    # O cookie de refresh só vai por HTTPS fora de dev.
    cookie_secure: bool = False
    database_url: str = "postgresql+asyncpg://aulas:aulas_local@db:5432/aulas_ingles"

    # Origens aceitas pelo CORS. Em dev a lista fica vazia de propósito:
    # o browser fala com /api na mesma origem, via proxy do Vite.
    cors_origins: list[str] = []

    def validar(self) -> None:
        """Erros de configuração que só podem estourar no boot, nunca em produção silenciosa."""
        if self.app_env == "prod" and self.jwt_secret.startswith("dev-apenas"):
            raise RuntimeError("JWT_SECRET precisa de um valor próprio quando APP_ENV=prod.")
        if len(self.jwt_secret.encode()) < 32:
            raise RuntimeError("JWT_SECRET precisa de pelo menos 32 bytes (RFC 7518, HS256).")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validar()
    return s
