"""Configuração da aplicação, lida do ambiente."""

from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.audio_upload import MAX_AUDIO_BYTES


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
    deployment_profile: Literal["local", "public"] = "local"
    public_origin: str | None = None
    legacy_writes_until: datetime = datetime(2026, 11, 13, tzinfo=UTC)
    auth_window_seconds: int = 300
    auth_identity_limit: int = 20
    auth_origin_limit: int = 200
    auth_hash_concurrency: int = 2
    database_url: str = "postgresql+asyncpg://aulas:aulas_local@db:5432/aulas_ingles"
    database_purpose: Literal["runtime", "worker", "migrator"] | None = None
    database_pool_size: int = Field(default=5, ge=1, le=20)
    database_max_overflow: int = Field(default=5, ge=0, le=20)
    database_process_budget: int = Field(default=2, ge=1, le=20)
    database_pool_timeout_seconds: int = Field(default=10, ge=1, le=60)
    database_statement_timeout_ms: int = Field(default=30_000, ge=1_000, le=120_000)
    database_lock_timeout_ms: int = Field(default=5_000, ge=100, le=30_000)
    # Enable only after the 40B.2a migration/permissions have been rehearsed.
    # Reads/exports of existing snapshots remain available when capture is off.
    editorial_snapshots_enabled: bool = False
    # Local rehearsal only; archive service also rejects prod/public profiles.
    editorial_archive_enabled: bool = False
    # Local rehearsal only; controlled reorder also requires an audited CLI apply.
    editorial_reorder_enabled: bool = False
    # Aggregate diagnostics only; never expose query counts on public/prod deployments.
    performance_probe_enabled: bool = False
    # Endpoint operacional agregado. Ausente = endpoint desabilitado.
    operations_token: str | None = None

    # As gravações ficam fora do PostgreSQL. O banco guarda somente metadados
    # e uma chave opaca gerada pelo servidor.
    speaking_storage_dir: str = "/app/data/speaking"
    speaking_max_bytes: int = Field(default=MAX_AUDIO_BYTES, ge=1, le=MAX_AUDIO_BYTES)

    # Recursos assistidos são experimentais, opt-in e ficam desligados sem
    # um gateway explicitamente configurado. O gateway recebe áudio bruto ou
    # texto/rubrica e devolve JSON no contrato documentado pelo serviço.
    assisted_features_enabled: bool = False
    assist_transcription_url: str | None = None
    assist_writing_url: str | None = None
    assist_provider_kind: Literal["gateway", "ollama"] = "gateway"
    assist_provider_name: str = "external"
    assist_provider_token: str | None = None
    assist_ollama_base_url: str = "http://host.docker.internal:11434"
    assist_ollama_model: str = "qwen2.5:7b"
    assist_daily_quota: int = 5
    assist_reservation_seconds: int = 900
    assist_retention_days: int = 30
    assist_timeout_seconds: int = 20
    assist_job_max_attempts: int = 3
    assist_job_retry_base_seconds: int = 5
    assist_job_stale_seconds: int = 120
    assist_worker_poll_seconds: float = 1.0
    maintenance_batch_size: int = Field(default=100, ge=1, le=500)
    maintenance_interval_seconds: int = Field(default=60, ge=10, le=3600)
    maintenance_cleanup_enabled: bool = False  # Opt-in para refresh/pending de 7 dias.

    # Origens aceitas pelo CORS. Em dev a lista fica vazia de propósito:
    # o browser fala com /api na mesma origem, via proxy do Vite.
    cors_origins: list[str] = []

    @property
    def database_connection_budget(self) -> int:
        """Teto declarado para API/workers somados no ambiente."""

        return self.database_process_budget * (self.database_pool_size + self.database_max_overflow)

    @property
    def writing_assist_configured(self) -> bool:
        if self.assist_provider_kind == "ollama":
            return bool(self.assist_ollama_base_url.strip() and self.assist_ollama_model.strip())
        return bool(self.assist_writing_url)

    def validar(self) -> None:
        """Erros de configuração que só podem estourar no boot, nunca em produção silenciosa."""
        if self.legacy_writes_until.tzinfo is None:
            raise RuntimeError("LEGACY_WRITES_UNTIL precisa incluir fuso horário.")
        if (
            min(
                self.auth_window_seconds,
                self.auth_identity_limit,
                self.auth_origin_limit,
                self.auth_hash_concurrency,
            )
            < 1
        ):
            raise RuntimeError("Limites de autenticação precisam ser positivos.")
        if self.deployment_profile == "public":
            origin = urlparse(self.public_origin or "")
            if not self.cookie_secure or origin.scheme != "https" or not origin.hostname:
                raise RuntimeError("Perfil público exige COOKIE_SECURE=true e PUBLIC_ORIGIN HTTPS.")
        if self.performance_probe_enabled and (
            self.app_env == "prod" or self.deployment_profile == "public"
        ):
            raise RuntimeError("PERFORMANCE_PROBE_ENABLED é exclusivo de ambiente local/teste.")
        if self.operations_token and len(self.operations_token.encode()) < 32:
            raise RuntimeError("OPERATIONS_TOKEN precisa de pelo menos 32 bytes.")
        if self.app_env == "prod" and self.jwt_secret.startswith("dev-apenas"):
            raise RuntimeError("JWT_SECRET precisa de um valor próprio quando APP_ENV=prod.")
        if len(self.jwt_secret.encode()) < 32:
            raise RuntimeError("JWT_SECRET precisa de pelo menos 32 bytes (RFC 7518, HS256).")
        if self.database_lock_timeout_ms >= self.database_statement_timeout_ms:
            raise RuntimeError(
                "DATABASE_LOCK_TIMEOUT_MS precisa ser menor que DATABASE_STATEMENT_TIMEOUT_MS."
            )
        if self.assist_daily_quota < 1:
            raise RuntimeError("ASSIST_DAILY_QUOTA precisa ser positivo.")
        if not 60 <= self.assist_reservation_seconds <= 3600:
            raise RuntimeError("ASSIST_RESERVATION_SECONDS deve ficar entre 60 e 3600 segundos.")
        if self.assist_retention_days < 1:
            raise RuntimeError("ASSIST_RETENTION_DAYS precisa ser positivo.")
        if self.assist_timeout_seconds < 1:
            raise RuntimeError("ASSIST_TIMEOUT_SECONDS precisa ser positivo.")
        if self.assist_job_max_attempts < 1:
            raise RuntimeError("ASSIST_JOB_MAX_ATTEMPTS precisa ser positivo.")
        if self.assist_job_retry_base_seconds < 0:
            raise RuntimeError("ASSIST_JOB_RETRY_BASE_SECONDS não pode ser negativo.")
        if self.assist_job_stale_seconds < self.assist_timeout_seconds:
            raise RuntimeError(
                "ASSIST_JOB_STALE_SECONDS precisa ser maior ou igual a ASSIST_TIMEOUT_SECONDS."
            )
        if self.assist_worker_poll_seconds <= 0:
            raise RuntimeError("ASSIST_WORKER_POLL_SECONDS precisa ser positivo.")
        if not self.assist_provider_name.strip() or len(self.assist_provider_name) > 80:
            raise RuntimeError("ASSIST_PROVIDER_NAME precisa ter entre 1 e 80 caracteres.")
        if self.assist_provider_kind == "ollama":
            parsed = urlparse(self.assist_ollama_base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise RuntimeError("ASSIST_OLLAMA_BASE_URL precisa ser uma URL HTTP válida.")
            if not self.assist_ollama_model.strip() or len(self.assist_ollama_model) > 120:
                raise RuntimeError("ASSIST_OLLAMA_MODEL precisa ter entre 1 e 120 caracteres.")
            if self.app_env == "prod" and parsed.hostname not in {
                "127.0.0.1",
                "localhost",
                "host.docker.internal",
            }:
                raise RuntimeError("Ollama precisa permanecer no host local em produção.")
        if self.app_env == "prod" and self.assisted_features_enabled:
            urls = [url for url in [self.assist_transcription_url, self.assist_writing_url] if url]
            if any(not url.startswith("https://") for url in urls):
                raise RuntimeError("Provedores assistidos precisam usar HTTPS em produção.")
            if self.assist_provider_kind == "gateway" and urls and not self.assist_provider_token:
                raise RuntimeError("ASSIST_PROVIDER_TOKEN é obrigatório em produção.")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validar()
    return s
