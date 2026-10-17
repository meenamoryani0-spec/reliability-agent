from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.tools.infrastructure_models import (
    DatabaseName,
    DeploymentId,
    ProjectRef,
    TeamId,
    validate_database_host,
)
from app.tools.models import WebsiteTarget
from app.tools.n8n_models import validate_n8n_url
from app.tools.targets import validate_addresses

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Validate configuration once during application creation.

    Environment variables override the repository-root .env file. Provider
    secrets are masked and never included in health responses or startup logs.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="forbid",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    nebius_api_key: SecretStr | None = Field(default=None, repr=False)
    nebius_model: str = Field(
        default="nvidia/Nemotron-3_5-Lightning",
        pattern=r"^nvidia/[A-Za-z0-9][A-Za-z0-9._-]{0,150}$",
    )
    nebius_timeout_seconds: float = Field(default=45, ge=1, le=60)
    nebius_max_tokens: int = Field(default=2048, ge=128, le=4096)
    investigation_mode: Literal["disabled", "fixture", "live"] = "disabled"
    website_targets: list[WebsiteTarget] = Field(default_factory=list, max_length=25)
    website_dns_nameservers: tuple[str, ...] = Field(default=(), max_length=3)
    n8n_mode: Literal["disabled", "fixture", "live"] = "disabled"
    n8n_base_url: str | None = Field(default=None, max_length=2048)
    n8n_api_key: SecretStr | None = Field(default=None, repr=False)
    n8n_timeout_seconds: float = Field(default=10, ge=1, le=30)
    n8n_dns_nameservers: tuple[str, ...] = Field(default=(), max_length=3)
    infrastructure_mode: Literal["disabled", "fixture", "live"] = "disabled"
    infrastructure_timeout_seconds: float = Field(default=10, ge=1, le=30)
    infrastructure_dns_nameservers: tuple[str, ...] = Field(default=(), max_length=3)
    vercel_token: SecretStr | None = Field(default=None, repr=False)
    vercel_deployment_id: DeploymentId | None = None
    vercel_team_id: TeamId | None = None
    supabase_access_token: SecretStr | None = Field(default=None, repr=False)
    supabase_project_ref: ProjectRef | None = None
    postgres_host: str | None = Field(default=None, max_length=253)
    postgres_port: Literal[5432, 6543] = 5432
    postgres_dbname: DatabaseName | None = None
    postgres_user: DatabaseName | None = None
    postgres_password: SecretStr | None = Field(default=None, repr=False)
    storage_mode: Literal["disabled", "local", "postgresql"] = "disabled"
    storage_sqlite_file: str = "work/data/reliability.sqlite3"
    storage_database_url: SecretStr | None = Field(default=None, repr=False)
    storage_allow_loopback: bool = False

    @field_validator("storage_database_url", mode="before")
    @classmethod
    def empty_storage_url(cls, value):
        return None if value == "" else value

    @field_validator("storage_sqlite_file")
    @classmethod
    def local_database_path(cls, value):
        path = Path(value)
        if path.is_absolute() or path.suffix != ".sqlite3":
            raise ValueError("Local database must be a project work/*.sqlite3 path")
        resolved = (PROJECT_ROOT / path).resolve()
        if not resolved.is_relative_to((PROJECT_ROOT / "work").resolve()):
            raise ValueError("Local database must stay inside project work/")
        return value

    @field_validator("postgres_port", mode="before")
    @classmethod
    def parse_postgres_port(cls, value):
        # Environment/dotenv values arrive as strings; Literal[int] does not coerce them.
        return int(value) if value in ("5432", "6543") else value

    @field_validator(
        "vercel_deployment_id",
        "vercel_team_id",
        "supabase_project_ref",
        "postgres_host",
        "postgres_dbname",
        "postgres_user",
        mode="before",
    )
    @classmethod
    def empty_optional_settings(cls, value):
        return None if value == "" else value

    @field_validator("postgres_host")
    @classmethod
    def validate_postgres_host(cls, value):
        return validate_database_host(value) if value is not None else None

    @field_validator("postgres_password", mode="before")
    @classmethod
    def validate_postgres_password(cls, value):
        if value == "":
            return None
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw, str) and ("\0" in raw or len(raw) > 1024):
            raise ValueError("PostgreSQL password is invalid")
        return value

    @field_validator("n8n_base_url", mode="before")
    @classmethod
    def validate_n8n_base(cls, value):
        if value is None or value == "":
            return None
        return validate_n8n_url(value)

    @field_validator(
        "website_dns_nameservers", "n8n_dns_nameservers", "infrastructure_dns_nameservers"
    )
    @classmethod
    def validate_nameservers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(validate_addresses(list(value))) if value else ()

    @model_validator(mode="after")
    def validate_target_ids(self) -> "Settings":
        if len({target.id for target in self.website_targets}) != len(self.website_targets):
            raise ValueError("Website target IDs must be unique")
        if self.environment == "production" and self.n8n_mode == "fixture":
            raise ValueError("Synthetic n8n mode is disabled in production")
        if self.investigation_mode == "fixture" and (
            self.environment == "production"
            or self.n8n_mode != "fixture"
            or self.infrastructure_mode != "fixture"
        ):
            raise ValueError(
                "Investigation fixtures require local n8n/infrastructure fixture modes"
            )
        if self.environment == "production" and self.infrastructure_mode == "fixture":
            raise ValueError("Synthetic infrastructure mode is disabled in production")
        if self.environment == "production" and (
            self.storage_mode == "local" or self.storage_allow_loopback
        ):
            raise ValueError("Local persistence settings are disabled in production")
        if self.storage_mode == "postgresql":
            from pydantic import TypeAdapter
            from sqlalchemy.engine import make_url
            from sqlalchemy.exc import ArgumentError

            if self.storage_database_url is None:
                raise ValueError("PostgreSQL application storage requires configuration")
            try:
                url = make_url(self.storage_database_url.get_secret_value())
                if (
                    url.drivername != "postgresql+psycopg"
                    or not url.host
                    or not url.database
                    or not url.username
                    or not url.password
                    or url.query
                ):
                    raise ValueError()
                TypeAdapter(DatabaseName).validate_python(url.database)
                TypeAdapter(DatabaseName).validate_python(url.username)
                if "\0" in url.password or len(url.password) > 1024:
                    raise ValueError()
                if url.host in {"127.0.0.1", "localhost"}:
                    if not self.storage_allow_loopback:
                        raise ValueError()
                else:
                    validate_database_host(url.host)
            except (ValueError, TypeError, ArgumentError):
                raise ValueError("Application database URL is invalid") from None
        return self

    @field_validator(
        "nebius_api_key", "n8n_api_key", "vercel_token", "supabase_access_token", mode="before"
    )
    @classmethod
    def normalize_api_key(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if not value.isascii() or any(character.isspace() for character in value):
                raise ValueError("API key must be ASCII without whitespace")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value
