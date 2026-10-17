"""Parse known execution metadata without copying names, errors, or node I/O."""

import hashlib

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.tools.models import CheckStatus
from app.tools.n8n_models import (
    Cursor,
    ExecutionEvidence,
    ExecutionId,
    ExecutionState,
    ExecutionSummary,
    NodeFailure,
    NodeObservation,
    ResourceId,
    WorkflowSummary,
)


class N8nError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"n8n inspection failed ({code})")


class ProviderMetadata(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", hide_input_in_errors=True)


class WorkflowMetadata(ProviderMetadata):
    id: ResourceId
    active: bool


class ExecutionMetadata(ProviderMetadata):
    id: ExecutionId
    workflowId: ResourceId
    status: ExecutionState
    startedAt: str | None
    stoppedAt: str | None


class ProviderPage(ProviderMetadata):
    data: list[dict] = Field(max_length=50)
    nextCursor: Cursor | None


class ExecutionLineage(ProviderMetadata):
    mode: str | None = Field(default=None, max_length=32, pattern=r"^[a-zA-Z]+$")
    retryOf: ExecutionId | None = None
    retrySuccessId: ExecutionId | None = None


class ErrorMetadata(ProviderMetadata):
    httpCode: str | int | None = None
    node: dict | None = None

    @field_validator("httpCode")
    @classmethod
    def validate_code(cls, value):
        if value is not None:
            if isinstance(value, bool) or not str(value).isdigit() or not 100 <= int(value) <= 599:
                raise ValueError("Invalid recorded HTTP status")
        return value


def workflow_summary(raw: dict) -> WorkflowSummary:
    metadata = WorkflowMetadata.model_validate(raw)
    return WorkflowSummary(id=metadata.id, active=metadata.active)


def execution_summary(raw: dict) -> ExecutionSummary:
    metadata = ExecutionMetadata.model_validate(raw)
    result = ExecutionSummary(
        id=metadata.id,
        workflow_id=metadata.workflowId,
        execution_state=metadata.status,
        started_at=metadata.startedAt,
        stopped_at=metadata.stoppedAt,
    )
    if any(
        value is not None and value.tzinfo is None
        for value in (result.started_at, result.stopped_at)
    ):
        raise N8nError("invalid_response")
    if result.started_at and result.stopped_at and result.stopped_at < result.started_at:
        raise N8nError("invalid_response")
    return result


def node_ref(name: str) -> str:
    if not isinstance(name, str) or not name or len(name) > 256:
        raise N8nError("invalid_response")
    return "node-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


def category(code: int | None) -> str:
    if code == 401:
        return "authentication_rejected"
    if code == 403:
        return "permission_denied"
    if code == 429:
        return "rate_limited"
    if code is not None and code >= 500:
        return "upstream_error"
    if code is not None and code >= 400:
        return "request_rejected"
    return "node_error" if code is None else "unknown"


def execution_evidence(raw: dict) -> ExecutionEvidence:
    metadata = execution_summary(raw)
    lineage = ExecutionLineage.model_validate(raw)
    status = {
        "error": CheckStatus.UNHEALTHY,
        "crashed": CheckStatus.UNHEALTHY,
        "success": CheckStatus.HEALTHY,
    }.get(metadata.execution_state, CheckStatus.UNKNOWN)
    summaries = {
        CheckStatus.UNHEALTHY: "Recorded execution failed; underlying root cause is unverified",
        CheckStatus.HEALTHY: "Recorded execution succeeded; business outcome was not checked",
        CheckStatus.UNKNOWN: "Execution state does not establish a completed business outcome",
    }
    result = ExecutionEvidence(
        **metadata.model_dump(),
        execution_mode=lineage.mode,
        retry_of=lineage.retryOf,
        retry_success_id=lineage.retrySuccessId,
        status=status,
        summary=summaries[status],
        data_availability="omitted",
    )
    if raw.get("dataTooLargeToDisplay") is True:
        result.data_availability = "oversized"
        return result
    data = raw.get("data")
    if data is None or data == {}:
        return result
    if not isinstance(data, dict):
        raise N8nError("invalid_response")
    if data.get("version") is not None and (
        type(data["version"]) is not int or data["version"] not in {0, 1}
    ):
        raise N8nError("unsupported_execution_data_version")
    redaction = data.get("redactionInfo", {})
    if redaction is None:
        redaction = {}
    if not isinstance(redaction, dict):
        raise N8nError("invalid_response")
    result.data_availability = "redacted" if redaction.get("isRedacted") is True else "present"
    details = data.get("resultData")
    if details is None and result.data_availability == "redacted":
        return result
    if not isinstance(details, dict):
        raise N8nError("invalid_response")
    if metadata.execution_state == "success" and (
        details.get("error") is not None or details.get("redactedError") is not None
    ):
        raise N8nError("contradictory_execution_evidence")
    runs = details.get("runData", {})
    if not isinstance(runs, dict) or len(runs) > 100:
        raise N8nError("invalid_response")
    node_ids = {}
    workflow = raw.get("workflowData")
    if isinstance(workflow, dict):
        nodes = workflow.get("nodes", [])
        if not isinstance(nodes, list) or len(nodes) > 100:
            raise N8nError("invalid_response")
        for node in nodes:
            if not isinstance(node, dict):
                raise N8nError("invalid_response")
            name = node.get("name")
            if name is not None:
                ref = node_ref(name)
                # Validate identifiers without retaining parameters or credentials.
                identifier = node.get("id")
                if identifier is not None:
                    parsed = WorkflowSummary(id=identifier, active=False)
                    if ref in node_ids:
                        raise N8nError("invalid_response")
                    node_ids[ref] = parsed.id

    def failure(error: object, *, name=None, index=None, redacted=False, global_error=False):
        if not isinstance(error, dict):
            raise N8nError("invalid_response")
        parsed = ErrorMetadata.model_validate(error)
        reported_name = parsed.node.get("name") if parsed.node else None
        if reported_name is not None:
            if name is not None and name != reported_name:
                raise N8nError("invalid_response")
            name = reported_name
        ref = node_ref(name) if name is not None else None
        code = int(parsed.httpCode) if parsed.httpCode is not None else None
        source = "result_error" if global_error else "node_error"
        if redacted:
            source = "redacted_" + source
        result.failures.append(
            NodeFailure(
                node_ref=ref,
                node_id=node_ids.get(ref),
                run_index=index,
                source=source,
                http_status=code,
                category=category(code),
            )
        )
        if len(result.failures) > 25:
            raise N8nError("invalid_response")

    for name, attempts in runs.items():
        ref = node_ref(name)
        if not isinstance(attempts, list) or not 1 <= len(attempts) <= 100:
            raise N8nError("invalid_response")
        failures, successes = 0, 0
        for index, attempt in enumerate(attempts):
            if not isinstance(attempt, dict):
                raise N8nError("invalid_response")
            if attempt.get("error") is not None:
                failure(attempt["error"], name=name, index=index)
                failures += 1
            elif attempt.get("redactedError") is not None:
                failure(attempt["redactedError"], name=name, index=index, redacted=True)
                failures += 1
            elif attempt.get("executionStatus") == "error":
                failure({}, name=name, index=index)
                failures += 1
            elif attempt.get("executionStatus") == "success":
                successes += 1
        result.observed_nodes.append(
            NodeObservation(
                node_ref=ref,
                node_id=node_ids.get(ref),
                attempts=len(attempts),
                failed_attempts=failures,
                successful_attempts=successes,
            )
        )
    if details.get("error") is not None:
        failure(details["error"], global_error=True)
    elif details.get("redactedError") is not None:
        failure(details["redactedError"], global_error=True, redacted=True)
    last = details.get("lastNodeExecuted")
    if last is not None:
        result.last_node_ref = node_ref(last)
    return result


def normalize_errors(operation):
    """Kept at service boundary: invalid provider metadata is never a diagnosis."""
    try:
        return operation()
    except (ValidationError, TypeError, ValueError, KeyError, RecursionError):
        raise N8nError("invalid_response") from None
