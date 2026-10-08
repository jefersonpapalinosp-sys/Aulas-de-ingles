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

    # As gravações ficam fora do PostgreSQL. O banco guarda somente metadados
    # e uma chave opaca gerada pelo servidor.
    speaking_storage_dir: str = "/app/data/speaking"
    speaking_max_bytes: int = 2_000_000

    # Recursos assistidos são experimentais, opt-in e ficam desligados sem
    # um gateway explicitamente configurado. O gateway recebe áudio bruto ou
    # texto/rubrica e devolve JSON no contrato documentado pelo serviço.
    assisted_features_enabled: bool = False
    assist_transcription_url: str | None = None
    assist_writing_url: str | None = None
    assist_provider_name: str = "external"
    assist_provider_token: str | None = None
    assist_daily_quota: int = 5
    assist_retention_days: int = 30
    assist_timeout_seconds: int = 20

    # Origens aceitas pelo CORS. Em dev a lista fica vazia de propósito:
    # o browser fala com /api na mesma origem, via proxy do Vite.
    cors_origins: list[str] = []

    def validar(self) -> None:
        """Erros de configuração que só podem estourar no boot, nunca em produção silenciosa."""
        if self.app_env == "prod" and self.jwt_secret.startswith("dev-apenas"):
            raise RuntimeError("JWT_SECRET precisa de um valor próprio quando APP_ENV=prod.")
        if len(self.jwt_secret.encode()) < 32:
            raise RuntimeError("JWT_SECRET precisa de pelo menos 32 bytes (RFC 7518, HS256).")
        if self.assist_daily_quota < 1:
            raise RuntimeError("ASSIST_DAILY_QUOTA precisa ser positivo.")
        if self.assist_retention_days < 1:
            raise RuntimeError("ASSIST_RETENTION_DAYS precisa ser positivo.")
        if self.assist_timeout_seconds < 1:
            raise RuntimeError("ASSIST_TIMEOUT_SECONDS precisa ser positivo.")
        if not self.assist_provider_name.strip() or len(self.assist_provider_name) > 80:
            raise RuntimeError("ASSIST_PROVIDER_NAME precisa ter entre 1 e 80 caracteres.")
        if self.app_env == "prod" and self.assisted_features_enabled:
            urls = [url for url in [self.assist_transcription_url, self.assist_writing_url] if url]
            if any(not url.startswith("https://") for url in urls):
                raise RuntimeError("Provedores assistidos precisam usar HTTPS em produção.")
            if urls and not self.assist_provider_token:
                raise RuntimeError("ASSIST_PROVIDER_TOKEN é obrigatório em produção.")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validar()
    return s
