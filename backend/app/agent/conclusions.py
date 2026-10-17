"""Check citations and support before accepting a model-selected hypothesis."""

from app.agent.investigation_models import ConclusionDraft
from app.agent.safety import load_object

SUMMARIES = {
    "authentication_rejection": "An n8n node recorded HTTP 401 authentication rejection.",
    "permission_rejection": "An n8n node recorded HTTP 403 permission rejection.",
    "rate_limiting": "A recorded request was rate limited.",
    "upstream_error": "An n8n node recorded an upstream HTTP error.",
    "workflow_failure": "A recorded n8n execution failed.",
    "website_failure": "A website or synthetic browser check observed a failure.",
    "deployment_failure": "The configured deployment reported a failure state.",
    "infrastructure_failure": "A configured infrastructure check observed an unhealthy state.",
    "unknown": "The collected observations do not establish a specific cause.",
}


class ConclusionError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def supports(hypothesis, result):
    if result.status != "OK" or not result.data:
        return False
    data = result.data
    if hypothesis == "unknown":
        return True
    failed = data.get("status") == "UNHEALTHY"
    service = data.get("service")
    evidence = data.get("evidence", {})
    if hypothesis in {
        "authentication_rejection",
        "permission_rejection",
        "upstream_error",
        "rate_limiting",
    }:
        category = {
            "authentication_rejection": "authentication_rejected",
            "permission_rejection": "permission_denied",
            "upstream_error": "upstream_error",
            "rate_limiting": "rate_limited",
        }[hypothesis]
        expected = {
            "authentication_rejection": 401,
            "permission_rejection": 403,
            "rate_limiting": 429,
        }
        if service == "n8n" and failed:
            return any(
                failure.get("category") == category
                and (
                    failure.get("http_status") == expected[hypothesis]
                    if hypothesis in expected
                    else isinstance(failure.get("http_status"), int)
                    and failure["http_status"] >= 500
                )
                for failure in evidence.get("failures", [])
            )
        return (
            hypothesis == "rate_limiting"
            and service == "website"
            and evidence.get("http_status") == 429
        )
    if hypothesis == "workflow_failure":
        return service == "n8n" and failed
    if hypothesis == "website_failure":
        return service == "website" and failed
    if hypothesis == "deployment_failure":
        return (
            service == "infrastructure" and data.get("component") == "vercel-deployment" and failed
        )
    if hypothesis == "infrastructure_failure":
        return (
            service == "infrastructure"
            and data.get("component") in {"supabase-project", "supabase-health", "postgres"}
            and failed
        )
    return False


def validate_conclusion(raw, records):
    try:
        draft = ConclusionDraft.model_validate(load_object(raw, 8192))
    except (ValueError, TypeError, RecursionError):
        raise ConclusionError("invalid_final") from None
    if len(set(draft.evidence_ids)) != len(draft.evidence_ids):
        raise ConclusionError("invalid_citation")
    by_id = {record.id: record.result for record in records}
    if any(
        identifier not in by_id or by_id[identifier].status != "OK"
        for identifier in draft.evidence_ids
    ):
        raise ConclusionError("invalid_citation")
    if not any(supports(draft.hypothesis, by_id[identifier]) for identifier in draft.evidence_ids):
        raise ConclusionError("unsupported_hypothesis")
    return draft


def assessment(records):
    states = {
        record.result.data.get("status")
        for record in records
        if record.result.status == "OK" and record.result.data
    }
    if states & {"UNHEALTHY", "DEGRADED"}:
        return "observed_failure"
    if "HEALTHY" in states:
        return "no_failure_observed"
    return "insufficient_evidence"


def provenance(records):
    flags = {
        record.result.data["synthetic"]
        for record in records
        if record.result.status == "OK" and record.result.data and "synthetic" in record.result.data
    }
    return (
        "mixed"
        if len(flags) == 2
        else "synthetic_only"
        if flags == {True}
        else "non_synthetic"
        if flags == {False}
        else "no_observations"
    )
