from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "MedDataHub API"
    app_version: str = "0.2.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    secret_key: str = "dev-only-insecure-secret-change-via-SECRET_KEY"
    access_token_expire_minutes: int = 60
    allow_registration: bool = True

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "no-reply@meddatahub.local"
    smtp_use_tls: bool = True
    otp_ttl_seconds: int = 600
    otp_max_attempts: int = 5
    otp_request_cooldown_seconds: int = 60

    database_url: str = "sqlite:///./meddatahub.db"
    database_connect_timeout: int = 5
    sql_echo: bool = False

    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    max_upload_bytes: int = 25 * 1024 * 1024
    raw_storage_dir: Path = BACKEND_ROOT / "storage" / "raw"
    processed_storage_dir: Path = BACKEND_ROOT / "storage" / "processed"
    synthmed_storage_dir: Path = BACKEND_ROOT / "storage" / "synthmed"
    synthmed_ctgan_default_epochs: int = Field(default=20, ge=1, le=200)
    synthmed_ctgan_max_epochs: int = Field(default=200, ge=1, le=10000)
    synthmed_ctgan_default_batch_size: int = Field(default=100, ge=11, le=10000)
    synthmed_ctgan_max_records: int = Field(default=50000, ge=1, le=1000000)
    synthmed_generation_worker_count: int = Field(default=1, ge=1, le=8)
    synthmed_generation_inline: bool = False

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("api_v1_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        prefix = value.strip()
        if not prefix.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/'")
        return prefix.rstrip("/") or "/"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str, info) -> str:
        environment = info.data.get("environment")
        if environment == "production" and (
            not value.strip() or value.startswith("dev-only-insecure-secret")
        ):
            raise ValueError("SECRET_KEY must be set to a strong value in production")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
