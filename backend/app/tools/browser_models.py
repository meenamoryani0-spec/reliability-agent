"""Bounded, sanitized evidence for the two synthetic browser flows."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.tools.models import CheckResult

FLOW_IDS = ("booking-healthy", "booking-crm-failure")
FlowId = Literal["booking-healthy", "booking-crm-failure"]


class BrowserEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    synthetic: Literal[True] = True
    network_mode: Literal["intercepted_local_fixtures"] = "intercepted_local_fixtures"
    stage: Literal["launch", "navigation", "submit", "verification"] = "launch"
    reason: Literal[
        "confirmation_verified",
        "fixture_crm_auth_rejected",
        "browser_unavailable",
        "browser_timeout",
        "browser_execution_failed",
        "browser_worker_failed",
        "browser_worker_invalid_output",
        "browser_busy",
        "network_request_blocked",
        "confirmation_not_verified",
        "frontend_errors",
    ]
    browser_version: str | None = Field(default=None, pattern=r"^[0-9.]{1,40}$")
    navigation_http_status: int | None = Field(default=None, ge=100, le=599)
    booking_http_status: int | None = Field(default=None, ge=100, le=599)
    confirmation_visible: bool = False
    failure_visible: bool = False
    console_error_count: int = Field(default=0, ge=0, le=1000)
    page_error_count: int = Field(default=0, ge=0, le=1000)
    blocked_request_count: int = Field(default=0, ge=0, le=1000)


class BrowserFlowResult(CheckResult):
    check_type: Literal["browser"] = "browser"
    evidence: BrowserEvidence
