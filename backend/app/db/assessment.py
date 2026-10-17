"""Finite incident assessment vocabulary; no unverified root-cause narrative."""

from typing import Literal

from pydantic import Field, model_validator

from app.db.capture import CaptureSchema, RecordId

Hypothesis = Literal[
    "authentication_rejection",
    "permission_rejection",
    "rate_limiting",
    "upstream_error",
    "workflow_failure",
    "website_failure",
    "deployment_failure",
    "infrastructure_failure",
    "unknown",
]
NextStep = Literal[
    "inspect_authentication_configuration",
    "inspect_execution",
    "verify_business_flow",
    "inspect_website",
    "inspect_infrastructure",
    "collect_more_evidence",
]


class AssessmentDraft(CaptureSchema):
    check_id: RecordId
    hypothesis: Hypothesis
    recommended_steps: list[NextStep] = Field(min_length=1, max_length=5)
    inference_source: Literal["scripted_fixture", "nebius"]
    root_cause: None = None
    root_cause_verified: Literal[False] = False


class AssessmentCapture(CaptureSchema):
    status: Literal["disabled", "not_applicable", "saved", "unavailable"] = "not_applicable"
    check_ids: list[RecordId] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def confirmed_checks(self):
        if (self.status == "saved") != bool(self.check_ids):
            raise ValueError("Saved assessment requires confirmed check identifiers")
        if len(set(self.check_ids)) != len(self.check_ids):
            raise ValueError("Duplicate assessment identifiers")
        return self
