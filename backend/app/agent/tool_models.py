"""Strict model-facing arguments; provider configuration never comes from a call."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.capture import HistoryCapture
from app.tools.browser_models import FlowId
from app.tools.n8n_models import Cursor, ExecutionId, ResourceId


class Arguments(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class WebsiteArguments(Arguments):
    target_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,31}$")]


class FlowArguments(Arguments):
    flow_id: FlowId


class PageArguments(Arguments):
    limit: int = Field(default=25, ge=1, le=50)
    cursor: Cursor | None = None


class FailedExecutionsArguments(PageArguments):
    workflow_id: ResourceId | None = None


class ExecutionArguments(Arguments):
    execution_id: ExecutionId


class ToolResult(Arguments):
    # OK means dispatch completed, not that the observed service is healthy.
    name: str | None
    status: Literal["OK", "REJECTED", "EXECUTION_FAILED"]
    reason: (
        Literal[
            "access_disabled",
            "unknown_tool",
            "invalid_arguments",
            "arguments_too_large",
            "target_not_registered",
            "busy",
            "deadline_exceeded",
            "execution_failed",
            "invalid_result",
            "result_too_large",
            "unsafe_result",
        ]
        | None
    ) = None
    data: dict | None = None
    history: HistoryCapture = Field(default_factory=HistoryCapture)
