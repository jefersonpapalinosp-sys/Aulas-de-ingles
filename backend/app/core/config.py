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
    database_url: str = "postgresql+asyncpg://aulas:aulas_local@db:5432/aulas_ingles"

    # Origens aceitas pelo CORS. Em dev a lista fica vazia de propósito:
    # o browser fala com /api na mesma origem, via proxy do Vite.
    cors_origins: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
