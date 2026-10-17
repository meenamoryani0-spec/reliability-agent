import json

import pytest

from app.agent.conclusions import (
    ConclusionError,
    assessment,
    provenance,
    supports,
    validate_conclusion,
)
from app.agent.investigation_models import EvidenceRecord
from app.agent.tool_models import ToolResult


def result(service, status, **data):
    return ToolResult(name="test", status="OK", data={"service": service, "status": status, **data})


@pytest.mark.parametrize(
    "hypothesis,observation",
    [
        (
            "authentication_rejection",
            result(
                "n8n",
                "UNHEALTHY",
                evidence={
                    "failures": [{"category": "authentication_rejected", "http_status": 401}]
                },
            ),
        ),
        (
            "permission_rejection",
            result(
                "n8n",
                "UNHEALTHY",
                evidence={"failures": [{"category": "permission_denied", "http_status": 403}]},
            ),
        ),
        (
            "rate_limiting",
            result(
                "n8n",
                "UNHEALTHY",
                evidence={"failures": [{"category": "rate_limited", "http_status": 429}]},
            ),
        ),
        (
            "upstream_error",
            result(
                "n8n",
                "UNHEALTHY",
                evidence={"failures": [{"category": "upstream_error", "http_status": 502}]},
            ),
        ),
        ("rate_limiting", result("website", "DEGRADED", evidence={"http_status": 429})),
        ("workflow_failure", result("n8n", "UNHEALTHY")),
        ("website_failure", result("website", "UNHEALTHY")),
        (
            "deployment_failure",
            result("infrastructure", "UNHEALTHY", component="vercel-deployment"),
        ),
        (
            "infrastructure_failure",
            result("infrastructure", "UNHEALTHY", component="supabase-health"),
        ),
        (
            "infrastructure_failure",
            result("infrastructure", "UNHEALTHY", component="supabase-project"),
        ),
        ("infrastructure_failure", result("infrastructure", "UNHEALTHY", component="postgres")),
        ("unknown", result("n8n", "CHECK_FAILED")),
    ],
)
def test_each_hypothesis_requires_matching_observation(hypothesis, observation):
    assert supports(hypothesis, observation)
    assert not supports(hypothesis, ToolResult(name="test", status="EXECUTION_FAILED"))
    draft = validate_conclusion(
        json.dumps(
            {
                "hypothesis": hypothesis,
                "evidence_ids": ["e1"],
                "next_steps": ["collect_more_evidence"],
            }
        ),
        [EvidenceRecord(id="e1", result=observation)],
    )
    assert draft.hypothesis == hypothesis


@pytest.mark.parametrize(
    "hypothesis,observation",
    [
        (
            "authentication_rejection",
            result(
                "n8n",
                "CHECK_FAILED",
                evidence={
                    "failures": [{"category": "authentication_rejected", "http_status": 401}]
                },
            ),
        ),
        (
            "authentication_rejection",
            result(
                "n8n",
                "UNHEALTHY",
                evidence={"failures": [{"category": "permission_denied", "http_status": 403}]},
            ),
        ),
        (
            "permission_rejection",
            result(
                "n8n",
                "UNHEALTHY",
                evidence={"failures": [{"category": "permission_denied", "http_status": 401}]},
            ),
        ),
        (
            "upstream_error",
            result(
                "n8n",
                "UNHEALTHY",
                evidence={"failures": [{"category": "upstream_error", "http_status": 429}]},
            ),
        ),
        (
            "upstream_error",
            result(
                "n8n",
                "UNHEALTHY",
                evidence={"failures": [{"category": "upstream_error", "http_status": None}]},
            ),
        ),
        ("deployment_failure", result("infrastructure", "UNKNOWN", component="vercel-events")),
        ("infrastructure_failure", result("infrastructure", "CHECK_FAILED", component="postgres")),
        (
            "infrastructure_failure",
            result("infrastructure", "UNHEALTHY", component="vercel-deployment"),
        ),
        ("website_failure", result("n8n", "UNHEALTHY")),
    ],
)
def test_unrelated_or_unverified_evidence_cannot_support_failure(hypothesis, observation):
    assert not supports(hypothesis, observation)
    with pytest.raises(ConclusionError, match="unsupported_hypothesis"):
        validate_conclusion(
            json.dumps(
                {
                    "hypothesis": hypothesis,
                    "evidence_ids": ["e1"],
                    "next_steps": ["collect_more_evidence"],
                }
            ),
            [EvidenceRecord(id="e1", result=observation)],
        )


@pytest.mark.parametrize(
    "states,expected",
    [
        (["HEALTHY", "UNHEALTHY"], "observed_failure"),
        (["DEGRADED"], "observed_failure"),
        (["HEALTHY", "UNKNOWN"], "no_failure_observed"),
        (["CHECK_FAILED", "UNKNOWN"], "insufficient_evidence"),
        ([], "insufficient_evidence"),
    ],
)
def test_assessment_is_computed_from_observations_not_model_assertions(states, expected):
    records = [
        EvidenceRecord(id=f"e{index + 1}", result=result("website", status))
        for index, status in enumerate(states)
    ]
    assert assessment(records) == expected


@pytest.mark.parametrize(
    "flags,expected",
    [
        ([], "no_observations"),
        ([True], "synthetic_only"),
        ([False], "non_synthetic"),
        ([True, False], "mixed"),
    ],
)
def test_provenance_comes_from_tool_evidence(flags, expected):
    records = [
        EvidenceRecord(id=f"e{index + 1}", result=result("website", "UNKNOWN", synthetic=flag))
        for index, flag in enumerate(flags)
    ]
    assert provenance(records) == expected
