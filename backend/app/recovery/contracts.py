from typing import Literal

from pydantic import Field, model_validator

from app.db.capture import CaptureSchema
from app.tools.n8n_models import ResourceId

VerificationResult = Literal["VERIFIED", "NOT_RECOVERED", "INCONCLUSIVE"]
VerificationReason = Literal[
    "required_path_succeeded",
    "execution_not_finished",
    "execution_failed",
    "read_unavailable",
    "identity_mismatch",
    "missing_execution_data",
    "missing_required_nodes",
    "node_not_successful",
    "completion_node_not_observed",
    "invalid_timestamps",
    "completion_stale",
    "observation_stale",
    "original_failure_not_covered",
    "additional_failure",
    "policy_changed",
]


class FlowPolicy(CaptureSchema):
    required_node_ids: list[ResourceId] = Field(min_length=2, max_length=25)
    completion_node_id: ResourceId

    @model_validator(mode="after")
    def distinct_completion(self):
        if len(set(self.required_node_ids)) != len(self.required_node_ids):
            raise ValueError("Required node IDs must be unique")
        if self.completion_node_id not in self.required_node_ids:
            raise ValueError("Completion node must be required")
        return self


class Decision(CaptureSchema):
    result: VerificationResult
    reason: VerificationReason
