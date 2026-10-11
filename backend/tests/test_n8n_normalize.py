import pytest

from app.tools.n8n_fixtures import PRIVATE_CANARY, execution_record
from app.tools.n8n_normalize import N8nError, execution_evidence, normalize_errors


def parse(record):
    return normalize_errors(lambda: execution_evidence(record))


def test_error_evidence_and_missing_downstream_run():
    result = parse(execution_record("1001", failed=True))
    assert result.status == "UNHEALTHY"
    assert {node.node_id for node in result.observed_nodes} == {"trigger", "crm"}
    assert result.failures[0].node_id == "crm"
    assert result.failures[0].http_status == 401
    assert result.failures[0].category == "authentication_rejected"
    assert result.failures[0].source == "node_error"
    assert not result.root_cause_verified
    assert not result.business_outcome_verified
    serialized = result.model_dump_json()
    for forbidden in [
        PRIVATE_CANARY,
        "NodeApiError",
        "Booking request",
        "Send confirmation",
        "parameters",
        "credentials",
        "description",
        "message",
        "stack",
    ]:
        assert forbidden not in serialized


def test_success_is_only_recorded_execution_success():
    result = parse(execution_record("1002", failed=False))
    assert result.status == "HEALTHY"
    assert {node.node_id for node in result.observed_nodes} == {"trigger", "crm", "confirmation"}
    assert result.failures == []
    assert not result.business_outcome_verified


@pytest.mark.parametrize(
    ("code", "category"),
    [
        ("401", "authentication_rejected"),
        (403, "permission_denied"),
        ("429", "rate_limited"),
        ("503", "upstream_error"),
        (400, "request_rejected"),
        (None, "node_error"),
    ],
)
def test_categories_require_recorded_http_status(code, category):
    record = execution_record("1001", failed=True)
    record["data"]["resultData"]["runData"]["CRM"][0]["error"] = {
        "httpCode": code,
        "message": "expired revoked invalid credentials",
    }
    record["data"]["resultData"].pop("error")
    result = parse(record)
    assert result.failures[0].category == category
    assert not result.root_cause_verified


@pytest.mark.parametrize("state", ["waiting", "running", "new", "canceled", "unknown"])
def test_nonterminal_or_indeterminate_states_are_not_healthy(state):
    record = execution_record("1002", failed=False)
    record["status"] = state
    result = parse(record)
    assert result.status == "UNKNOWN"


@pytest.mark.parametrize("case", ["missing", "oversized", "redacted"])
def test_recorded_failure_survives_missing_details_without_inventing_cause(case):
    record = execution_record("1001", failed=True)
    if case == "missing":
        record.pop("data")
    elif case == "oversized":
        record["dataTooLargeToDisplay"] = True
    else:
        record["data"] = {"redactionInfo": {"isRedacted": True}}
    result = parse(record)
    assert result.status == "UNHEALTHY"
    assert (
        result.data_availability
        == {"missing": "omitted", "oversized": "oversized", "redacted": "redacted"}[case]
    )
    assert not result.failures
    assert not result.observed_nodes


def test_redacted_errors_use_only_technical_code_and_do_not_reveal():
    record = execution_record("1001", failed=True)
    record["data"] = {
        "redactionInfo": {"isRedacted": True},
        "resultData": {
            "runData": {"CRM": [{"redactedError": {"type": "NodeApiError", "httpCode": "403"}}]},
            "redactedError": {"type": "NodeApiError", "httpCode": "403"},
        },
    }
    result = parse(record)
    assert result.data_availability == "redacted"
    assert result.failures[0].category == "permission_denied"
    assert result.failures[0].source == "redacted_node_error"


def test_last_node_is_not_assumed_to_be_a_failed_node():
    record = execution_record("1001", failed=True)
    record["data"]["resultData"] = {"runData": {}, "lastNodeExecuted": "CRM"}
    result = parse(record)
    assert result.last_node_ref
    assert result.failures == []


def test_each_attempt_is_preserved_without_assuming_a_retry_recovered_business():
    record = execution_record("1002", failed=False)
    record["data"]["resultData"]["runData"]["CRM"] = [
        {"error": {"httpCode": "401"}},
        {"executionStatus": "success"},
    ]
    result = parse(record)
    assert result.status == "HEALTHY"
    assert result.observed_nodes[1].attempts == 2
    assert result.observed_nodes[1].failed_attempts == 1
    assert result.failures[0].run_index == 0
    assert not result.business_outcome_verified


def test_contradictory_global_error_and_success_are_not_healthy():
    record = execution_record("1001", failed=True)
    record["status"] = "success"
    with pytest.raises(N8nError, match="contradictory_execution_evidence"):
        parse(record)


@pytest.mark.parametrize("version", [2, True, "1"])
def test_unknown_execution_data_versions_are_not_assumed_compatible(version):
    record = execution_record("1001", failed=True)
    record["data"]["version"] = version
    with pytest.raises(N8nError, match="unsupported_execution_data_version"):
        parse(record)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda x: x.update(status="future_state"),
        lambda x: x.update(startedAt="nonsense"),
        lambda x: x.update(startedAt="2026-10-12T00:00:00Z"),
        lambda x: x.update(startedAt="2026-10-11T00:00:00"),
        lambda x: x.update(data="untrusted string"),
        lambda x: x["data"]["resultData"].update(runData=[]),
        lambda x: x["data"]["resultData"].update(runData={"CRM": "bad attempts"}),
        lambda x: x["data"]["resultData"].update(
            runData={"CRM": [{"error": {"httpCode": "SECRET"}}]}
        ),
        lambda x: x["data"]["resultData"].update(runData={"CRM": [{"error": {"httpCode": True}}]}),
        lambda x: x["data"]["resultData"].update(
            runData={"CRM": [{"error": {"node": {"name": "other"}}}]}
        ),
        lambda x: x["data"]["resultData"].update(runData={"CRM": [{"error": {}}] * 101}),
    ],
)
def test_malformed_or_unsupported_data_is_not_a_diagnosis(mutation):
    record = execution_record("1001", failed=True)
    mutation(record)
    with pytest.raises(N8nError, match="invalid_response"):
        parse(record)
