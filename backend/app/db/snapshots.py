"""Project only normalized check evidence into bounded history records."""

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.tools.browser_models import BrowserFlowResult
from app.tools.infrastructure_models import InfrastructureResult
from app.tools.models import CheckResult, CheckStatus
from app.tools.n8n_models import N8nReadResult

WEBSITE_EVIDENCE = {
    "reason",
    "hostname",
    "addresses",
    "http_status",
    "redirect_count",
    "status_chain",
    "probed_ip",
    "expected_statuses",
    "expires_at",
    "days_remaining",
    "tls_version",
    "verify_code",
}
INFRASTRUCTURE_EVIDENCE = {
    "deployment_id",
    "ready_state",
    "scope",
    "production_alias_verified",
    "events",
    "sample_only",
    "limit",
    "limit_reached",
    "project_ref",
    "state",
    "services",
    "select_one",
    "read_only_verified",
    "tls_policy",
}


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    category: Literal["website", "n8n", "infrastructure"]
    component: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,100}$")
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    synthetic: bool
    kind: str = Field(pattern=r"^[a-z_]{1,32}$")
    status: CheckStatus
    observed_at: datetime
    payload: dict

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone-aware observation required")
        return value

    @field_validator("payload")
    @classmethod
    def bounded_payload(cls, value):
        if len(json.dumps(value, allow_nan=False).encode()) > 65536:
            raise ValueError("History evidence exceeds its size limit")
        return value

    @property
    def service_id(self):
        identity = (
            f"reliability:{self.category}:{self.component}:{self.synthetic}:{self.source_hash}"
        )
        return str(uuid5(NAMESPACE_URL, identity))


def snapshot_for(result, source: str) -> Snapshot:
    synthetic = False
    if isinstance(result, InfrastructureResult):
        category, component, kind = "infrastructure", result.component, result.check_type
        synthetic, status = result.synthetic, result.status
        evidence = {
            key: value for key, value in result.evidence.items() if key in INFRASTRUCTURE_EVIDENCE
        }
        for collection, keys in (
            ("events", {"type", "created_ms"}),
            ("services", {"name", "state"}),
        ):
            if collection in evidence:
                evidence[collection] = [
                    {key: value for key, value in row.items() if key in keys}
                    for row in evidence[collection]
                    if isinstance(row, dict)
                ]
    elif isinstance(result, N8nReadResult):
        if result.operation != "execution":
            raise ValueError("n8n list metadata is not a service health observation")
        category, kind, synthetic = "n8n", "execution", result.synthetic
        if result.execution is not None:
            component, status = "workflow:" + result.execution.workflow_id, result.execution.status
            evidence = result.execution.model_dump(mode="json", exclude={"summary"})
        else:
            component, status = "configured-n8n", CheckStatus.CHECK_FAILED
            evidence = {"reason": result.reason}
    elif isinstance(result, CheckResult):
        category, component, kind, status = (
            "website",
            result.component,
            result.check_type,
            result.status,
        )
        if isinstance(result, BrowserFlowResult):
            synthetic = True
            evidence = result.evidence.model_dump(mode="json")
        else:
            evidence = {
                key: value for key, value in result.evidence.items() if key in WEBSITE_EVIDENCE
            }
    else:
        raise ValueError("Unsupported history result")
    return Snapshot(
        category=category,
        component=component,
        kind=kind,
        status=status,
        synthetic=synthetic,
        source_hash=hashlib.sha256(source.encode()).hexdigest(),
        observed_at=result.checked_at,
        payload={
            "evidence": evidence,
            "root_cause_verified": False,
            "business_outcome_verified": False,
        },
    )
