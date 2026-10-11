"""Allowlisted n8n metadata; provider payloads and free-text errors stay private."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.tools.models import CheckStatus
from app.tools.targets import TargetError, parse_url

ResourceId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ExecutionId = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")]
Cursor = Annotated[str, Field(pattern=r"^[A-Za-z0-9_+/=-]{1,2048}$")]
ExecutionState = Literal[
    "canceled", "crashed", "error", "new", "running", "success", "unknown", "waiting"
]


def validate_n8n_url(value: str) -> str:
    url = parse_url(value)
    if url.scheme != "https" or not url.path.rstrip("/").endswith("/api/v1"):
        raise TargetError("n8n_https_api_root_required")
    return str(url).rstrip("/") + "/"


class SafeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class WorkflowSummary(SafeModel):
    id: ResourceId
    active: bool


class ExecutionSummary(SafeModel):
    id: ExecutionId
    workflow_id: ResourceId
    execution_state: ExecutionState
    started_at: datetime | None
    stopped_at: datetime | None


class NodeObservation(SafeModel):
    node_ref: str
    node_id: ResourceId | None = None
    attempts: int
    failed_attempts: int


class NodeFailure(SafeModel):
    node_ref: str | None = None
    node_id: ResourceId | None = None
    run_index: int | None = None
    source: Literal["node_error", "result_error", "redacted_node_error", "redacted_result_error"]
    http_status: int | None = None
    category: Literal[
        "authentication_rejected",
        "permission_denied",
        "rate_limited",
        "upstream_error",
        "request_rejected",
        "node_error",
        "unknown",
    ]


class ExecutionEvidence(ExecutionSummary):
    status: CheckStatus
    summary: str
    data_availability: Literal["present", "omitted", "redacted", "oversized"]
    observed_nodes: list[NodeObservation] = Field(default_factory=list)
    failures: list[NodeFailure] = Field(default_factory=list)
    last_node_ref: str | None = None
    root_cause_verified: Literal[False] = False
    business_outcome_verified: Literal[False] = False


class N8nReadResult(SafeModel):
    service: Literal["n8n"] = "n8n"
    operation: Literal["workflows", "failed_executions", "execution"]
    status: Literal["OK", "CHECK_FAILED"]
    synthetic: bool
    reason: str | None = None
    workflows: list[WorkflowSummary] = Field(default_factory=list)
    executions: list[ExecutionSummary] = Field(default_factory=list)
    execution: ExecutionEvidence | None = None
    next_cursor: Cursor | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
