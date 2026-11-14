"""Application settings, loaded from environment variables and an optional .env file."""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "HVAC AI Receptionist"
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"

    # Comma-separated list of allowed dashboard origins, e.g. "http://a.com,http://b.com".
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # Runtime connection: a NON-owner role, so Postgres row-level security always applies.
    database_url: SecretStr | None = None
    # Owner role, direct connection. Used only by Alembic migrations.
    migrations_database_url: SecretStr | None = None
    # Name of the runtime role that migrations grant table privileges to.
    app_db_role: str = Field(default="app_user", pattern=r"^[a-z_][a-z0-9_]{0,62}$")

    # Signs session tokens. Required for auth; rotate to invalidate every session.
    secret_key: SecretStr | None = None
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    allow_public_signup: bool = True
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    sentry_dsn: SecretStr | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def docs_enabled(self) -> bool:
        return not self.is_production

    @property
    def secure_cookies(self) -> bool:
        """Local dev runs on http://localhost, everything else is HTTPS-only."""
        return self.environment not in (Environment.LOCAL, Environment.TEST)


@lru_cache
def get_settings() -> Settings:
    return Settings()
