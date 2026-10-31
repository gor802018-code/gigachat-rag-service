"""Application configuration loaded from environment variables and ``.env``."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]
LLMProvider = Literal["gigachat", "openai", "deepseek"]

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    """Typed application settings.

    Values are resolved in this order: init arguments, environment variables,
    ``.env`` file, field defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Environment = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"
    db_echo: bool = False

    jwt_secret_key: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, gt=0, le=24 * 60)

    llm_provider: LLMProvider = "gigachat"
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    gigachat_credentials: SecretStr | None = None
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat"
    gigachat_verify_ssl_certs: bool = False
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_timeout_seconds: int = Field(default=60, gt=0)

    embedding_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    faiss_index_path: Path = Path("data/faiss_index")
    retriever_top_k: int = Field(default=4, gt=0, le=20)

    chunk_size: int = Field(default=1000, gt=0)
    chunk_overlap: int = Field(default=200, ge=0)
    max_upload_size_mb: int = Field(default=20, gt=0)

    @model_validator(mode="after")
    def _validate_consistency(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            msg = "CHUNK_OVERLAP must be smaller than CHUNK_SIZE"
            raise ValueError(msg)
        if self.is_production and self.jwt_secret_key.get_secret_value() == DEV_JWT_SECRET:
            msg = "JWT_SECRET_KEY must be overridden in production"
            raise ValueError(msg)
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "test"

    @property
    def active_llm_model(self) -> str:
        """Model name for the configured provider (``LLM_MODEL`` wins)."""
        if self.llm_model:
            return self.llm_model
        defaults = {
            "gigachat": self.gigachat_model,
            "openai": "gpt-4o-mini",
            "deepseek": "deepseek-chat",
        }
        return defaults[self.llm_provider]

    @property
    def upload_limit_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings instance (used as a FastAPI dependency)."""
    return Settings()
