"""Bounded infrastructure configuration and evidence, without provider payloads."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.tools.models import CheckStatus
from app.tools.targets import parse_url

DeploymentId = Annotated[str, Field(pattern=r"^dpl_[A-Za-z0-9]{1,100}$")]
TeamId = Annotated[str, Field(pattern=r"^team_[A-Za-z0-9]{1,100}$")]
ProjectRef = Annotated[str, Field(pattern=r"^[a-z]{20}$")]
DatabaseName = Annotated[str, Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")]
CheckId = Literal[
    "vercel-deployment", "vercel-events", "supabase-project", "supabase-health", "postgres"
]
CHECK_IDS = (
    "vercel-deployment",
    "vercel-events",
    "supabase-project",
    "supabase-health",
    "postgres",
)


def validate_database_host(value: str) -> str:
    # A single operator-configured DNS hostname, never a DSN, IP or socket path.
    url = parse_url("https://" + value)
    if url.host != value or url.path != "/" or url.port is not None:
        raise ValueError("PostgreSQL host must be a single lowercase DNS hostname")
    return value


class InfrastructureResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["infrastructure"] = "infrastructure"
    component: CheckId
    check_type: Literal["deployment", "events", "project", "service_health", "connectivity"]
    inspection: Literal["OK", "CHECK_FAILED"] = "OK"
    status: CheckStatus
    severity: Literal["none", "warning", "high"] = "none"
    summary: str
    synthetic: bool = False
    reason: str | None = None
    evidence: dict = Field(default_factory=dict)
    root_cause_verified: Literal[False] = False
    business_outcome_verified: Literal[False] = False
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def healthy(self) -> bool | None:
        if self.status == CheckStatus.HEALTHY:
            return True
        if self.status == CheckStatus.UNHEALTHY:
            return False
        return None


class InfrastructureError(ValueError):
    """Only fixed, safe categories may escape the adapter boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
