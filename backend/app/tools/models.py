from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.tools.targets import parse_url


class CheckStatus(StrEnum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"
    CHECK_FAILED = "CHECK_FAILED"


class CheckType(StrEnum):
    HTTP = "http"
    DNS = "dns"
    SSL = "ssl"


class WebsiteTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,31}$")
    url: str = Field(min_length=1, max_length=2048)
    expected_statuses: tuple[int, ...] = (200,)
    latency_warning_ms: int = Field(default=2000, ge=1, le=60000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return str(parse_url(value))

    @field_validator("expected_statuses")
    @classmethod
    def validate_statuses(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or len(value) > 10 or any(code < 200 or code > 299 for code in value):
            raise ValueError("Expected statuses must contain 1–10 HTTP success codes")
        return value


class CheckResult(BaseModel):
    service: str = "website"
    component: str
    check_type: CheckType
    status: CheckStatus
    severity: str = "none"
    summary: str
    evidence: dict = Field(default_factory=dict)
    latency_ms: float | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def healthy(self) -> bool | None:
        if self.status == CheckStatus.HEALTHY:
            return True
        if self.status == CheckStatus.UNHEALTHY:
            return False
        return None
