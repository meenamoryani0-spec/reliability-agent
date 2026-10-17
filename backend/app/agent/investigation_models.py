"""Evidence-linked conclusions; model prose never becomes a verified cause."""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.agent.tool_models import Arguments, ToolResult

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
EvidenceId = Annotated[str, Field(pattern=r"^e[1-8]$")]


class InvestigationRequest(Arguments):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def nonempty_question(cls, value):
        value = value.strip()
        if not value or len(value.encode("utf-8")) > 3000:
            raise ValueError("Invalid question")
        return value


class ConclusionDraft(Arguments):
    hypothesis: Hypothesis
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=8)
    next_steps: list[NextStep] = Field(min_length=1, max_length=5)


class EvidenceRecord(Arguments):
    id: EvidenceId
    result: ToolResult


class InvestigationReport(Arguments):
    status: Literal["COMPLETED", "INCOMPLETE", "CHECK_FAILED", "REJECTED"]
    reason: (
        Literal[
            "disabled",
            "missing_api_key",
            "busy",
            "access_disabled",
            "invalid_question",
            "fixture_question_unsupported",
            "sensitive_input",
            "provider_error",
            "invalid_final",
            "unsupported_hypothesis",
            "invalid_citation",
            "no_evidence",
            "model_budget_exhausted",
            "tool_budget_exhausted",
            "evidence_budget_exhausted",
            "context_budget_exhausted",
            "tool_not_allowed",
            "duplicate_tool_id",
            "repeated_tool_call",
            "tool_failed",
            "deadline_exceeded",
            "cancelled",
            "execution_failed",
            "unsafe_model_output",
        ]
        | None
    ) = None
    inference_source: Literal["disabled", "scripted_fixture", "nebius"]
    model: str | None = None
    assessment: Literal["observed_failure", "no_failure_observed", "insufficient_evidence"] = (
        "insufficient_evidence"
    )
    hypothesis: Hypothesis | None = None
    summary: str = (
        "Investigation did not reach a validated conclusion. "
        "Collected observations remain available."
    )
    cited_evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=8)
    next_steps: list[NextStep] = Field(default_factory=list, max_length=5)
    evidence: list[EvidenceRecord] = Field(default_factory=list, max_length=8)
    model_requests: int = Field(default=0, ge=0, le=6)
    tool_calls: int = Field(default=0, ge=0, le=8)
    evidence_provenance: Literal["no_observations", "synthetic_only", "non_synthetic", "mixed"] = (
        "no_observations"
    )
    root_cause_verified: Literal[False] = False
    business_outcome_verified: Literal[False] = False
    incident_created: Literal[False] = False
    remediation_executed: Literal[False] = False
