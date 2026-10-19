"""Receive minimal failure notifications from n8n's supported Error Trigger.

This is reported evidence, not an API poll or an authenticated business outcome.
No messages, stack traces, node input/output, or provider credentials are accepted.
"""

import hashlib
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from app.agent.safety import configured_secrets, contains_secret, load_object
from app.db.repository import StorageError
from app.db.snapshots import Snapshot
from app.security import require_authenticated
from app.tools.n8n_models import ExecutionId, ResourceId

router = APIRouter(tags=["n8n failure reports"])


class FailureReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    workflow_id: ResourceId
    execution_id: ExecutionId


def event_source(config):
    return hashlib.sha256(("n8n-error-trigger-v1:" + config.n8n_base_url).encode()).hexdigest()


async def recent_reports(history, config):
    if not config.n8n_events_enabled:
        return []
    # A bounded query for the configured workflows keeps API observations and
    # fixture sources out of this notification-only collection.
    services = []
    for workflow in sorted(set(config.n8n_events_workflow_ids)):
        service = Snapshot(
            category="n8n",
            component="workflow:" + workflow,
            source_hash=event_source(config),
            synthetic=False,
            kind="failure_report",
            status="UNHEALTHY",
            observed_at=datetime.now(UTC),
            payload={},
        )
        services.append(service.service_id)
    return await history.read("failure_reports", service_ids=services)


@router.get("/monitoring/n8n/reports")
async def read_reports(request: Request):
    require_authenticated(request)
    try:
        reports = await recent_reports(request.app.state.history, request.app.state.settings)
    except StorageError:
        raise HTTPException(503, "Report history unavailable") from None
    return {
        "reports": reports,
        "coverage": "received_failure_notifications_only",
        "absence_proves_health": False,
    }


@router.post("/integrations/n8n/failures")
async def ingest_failure(request: Request):
    if not getattr(request.state, "n8n_report_authenticated", False):
        raise HTTPException(404, "Access unavailable")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "JSON content required")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 1024:
            raise HTTPException(413, "Report is too large")
        body.extend(chunk)
    try:
        report = FailureReport.model_validate(load_object(bytes(body), 1024))
    except (ValidationError, ValueError, TypeError, RecursionError):
        raise HTTPException(422, "Invalid failure notification") from None
    config = request.app.state.settings
    if report.workflow_id not in config.n8n_events_workflow_ids or contains_secret(
        report.model_dump(), configured_secrets(config)
    ):
        raise HTTPException(422, "Workflow is not registered")
    source = event_source(config)
    identifier = str(uuid5(NAMESPACE_URL, f"{source}:{report.workflow_id}:{report.execution_id}"))
    snapshot = Snapshot(
        category="n8n",
        component="workflow:" + report.workflow_id,
        source_hash=source,
        synthetic=False,
        kind="failure_report",
        status="UNHEALTHY",
        observed_at=datetime.now(UTC),
        payload={
            "evidence": {
                **report.model_dump(),
                "provenance": "n8n_error_trigger_report",
                "received_at_is_execution_time": False,
                "execution_details_available": False,
            },
            "root_cause_verified": False,
            "business_outcome_verified": False,
        },
    )
    saved = await request.app.state.history.capture_report(snapshot, identifier)
    if saved.status != "saved":
        raise HTTPException(503, "Report could not be saved")
    return {
        "accepted": True,
        "check_id": saved.check_id,
        "incident": saved.incident.model_dump(mode="json"),
    }
