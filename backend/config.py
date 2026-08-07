"""Validated runtime configuration."""

from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """OpportunityEngine settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OPPORTUNITY_ENGINE_",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database_path: Path = Path("data/opportunity_engine.db")
    constitution_path: Path = Path("config/constitution.json")
    profile_path: Path = Path("config/profile.json")
    resume_storage_path: Path = Path("data/resumes")
    document_storage_path: Path = Path("data/documents")
    log_level: str = "INFO"
    enable_api_docs: bool = True
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @field_validator("host")
    @classmethod
    def require_loopback_host(cls, value: str) -> str:
        """Refuse network exposure in the approved v0.1 design."""
        try:
            address = ip_address(value)
        except ValueError as exc:
            raise ValueError("host must be a loopback IP address") from exc
        if not address.is_loopback:
            raise ValueError("v0.1 must bind to a loopback address")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("invalid log level")
        return normalized


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per process."""
    return Settings()

