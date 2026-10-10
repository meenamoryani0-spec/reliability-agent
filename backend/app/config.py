from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.tools.models import WebsiteTarget
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
    website_targets: list[WebsiteTarget] = Field(default_factory=list, max_length=25)
    website_dns_nameservers: tuple[str, ...] = Field(default=(), max_length=3)

    @field_validator("website_dns_nameservers")
    @classmethod
    def validate_nameservers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(validate_addresses(list(value))) if value else ()

    @model_validator(mode="after")
    def validate_target_ids(self) -> "Settings":
        if len({target.id for target in self.website_targets}) != len(self.website_targets):
            raise ValueError("Website target IDs must be unique")
        return self

    @field_validator("nebius_api_key", mode="before")
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
