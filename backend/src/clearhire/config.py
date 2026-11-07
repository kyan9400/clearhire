"""Settings, from environment variables prefixed CLEARHIRE_ (or a .env file)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "clearhire-development-secret-change-me-0123456789"  # noqa: S105 - refused when debug is off


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLEARHIRE_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://clearhire:clearhire@localhost:25432/clearhire"
    redis_url: str | None = None  # without Redis, background jobs run inside the API process
    embedding_model: str = "intfloat/multilingual-e5-small"
    ocr_languages: str = "eng+rus"
    storage_dir: Path = Path("data/files")

    jwt_secret: SecretStr = SecretStr(DEV_SECRET)
    access_ttl_minutes: int = Field(default=30, ge=1)
    refresh_ttl_days: int = Field(default=7, ge=1)
    debug: bool = False

    max_upload_mb: int = Field(default=10, ge=1, le=50)
    max_pages: int = Field(default=10, ge=1, le=50)
    retention_days: int = Field(default=365, ge=30)  # personal data kept this long after the last application
    blind_by_default: bool = True
    cors_origins: list[str] = ["http://localhost:4200", "http://localhost:3000"]
    demo_read_only: bool = False  # the public demo: staff can browse, nothing is changed or deleted

    # the AI assistant: any OpenAI-compatible chat endpoint (Ollama by default); empty turns it off
    llm_url: str | None = None
    llm_model: str = "qwen3.5:9b"
    llm_api_key: SecretStr | None = None
    llm_timeout: float = Field(default=120, gt=0)
    llm_calls_per_hour: int = Field(default=60, ge=1)  # per staff user

    @field_validator("llm_url", mode="before")
    @classmethod
    def _empty_is_off(cls, value: object) -> object:
        return value or None

    @field_validator("jwt_secret")
    @classmethod
    def _strong_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("CLEARHIRE_JWT_SECRET must be at least 32 characters")
        return value

    def check_production(self) -> None:
        if not self.debug and self.jwt_secret.get_secret_value() == DEV_SECRET:
            raise RuntimeError("Set CLEARHIRE_JWT_SECRET (or CLEARHIRE_DEBUG=1 for local development)")


@cache
def get_settings() -> Settings:
    return Settings()
