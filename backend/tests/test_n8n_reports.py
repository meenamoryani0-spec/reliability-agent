import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.conclusions import supports
from app.config import Settings
from app.main import create_app

TOKEN = "r" * 43
OPERATOR = "o" * 43
AUTH = {"Authorization": "Bearer " + TOKEN}
REPORT = {"workflow_id": "workflow-a", "execution_id": "123"}
PATH = "/integrations/n8n/failures"


def configured(base, **changes):
    values = base.model_dump()
    values.update(
        n8n_events_enabled=True,
        n8n_events_token=TOKEN,
        n8n_events_workflow_ids=["workflow-a"],
        n8n_base_url="https://n8n.example/api/v1/",
        incidents_enabled=True,
    )
    values.update(changes)
    return Settings(_env_file=None, **values)


def test_reports_are_persisted_deduplicated_and_distinct_from_api(database_config, engine):
    config = configured(database_config)
    with TestClient(create_app(config)) as client:
        first = client.post(PATH, headers=AUTH, json=REPORT)
        assert first.status_code == 200
        assert first.json()["accepted"] is True
        assert first.json()["incident"]["status"] == "created"
        before = client.get("/history/checks").json()[0]
        repeated = client.post(PATH, headers=AUTH, json=REPORT)
        assert repeated.json()["check_id"] == first.json()["check_id"]
        assert repeated.json()["incident"]["status"] == "existing"
        assert client.get("/history/checks").json() == [before]
        assert before["kind"] == "failure_report" and before["synthetic"] is False
        assert before["payload"]["evidence"]["received_at_is_execution_time"] is False
        assert before["payload"]["root_cause_verified"] is False
        assert client.get("/history/incidents").json()[0]["observation_count"] == 1
        result = client.get("/monitoring/n8n/reports").json()
        assert result["absence_proves_health"] is False
        assert result["reports"] == [before]
        assert client.get("/monitoring").json()["n8n"]["configured"] is False
        registry = client.app.state.tool_registry
        assert "read_n8n_failure_reports" in [d["function"]["name"] for d in registry.definitions()]
        read = asyncio.run(registry.execute("read_n8n_failure_reports", "{}"))
        assert read.status == "OK" and read.data["reports"][0]["check_id"] == before["id"]
        assert supports("workflow_failure", read) is True
        assert supports("authentication_rejection", read) is False
        assert TOKEN not in read.model_dump_json()
        assert len(client.get("/history/checks").json()) == 1
    with TestClient(create_app(config)) as reopened:
        assert reopened.post(PATH, headers=AUTH, json=REPORT).json()["check_id"] == before["id"]
        assert len(reopened.get("/monitoring/n8n/reports").json()["reports"]) == 1


def test_concurrent_report_retries_keep_one_observation(database_config, engine):
    with TestClient(create_app(configured(database_config))) as client:
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(
                pool.map(lambda _: client.post(PATH, headers=AUTH, json=REPORT), range(8))
            )
        assert all(response.status_code == 200 for response in responses)
        assert len({response.json()["check_id"] for response in responses}) == 1
        assert len(client.get("/history/checks").json()) == 1
        assert client.get("/history/incidents").json()[0]["observation_count"] == 1


def test_reports_accept_only_minimal_allowlisted_ids(database_config, engine):
    with TestClient(create_app(configured(database_config))) as client:
        for body in [
            {**REPORT, "message": "customer data"},
            {**REPORT, "error": {"stack": "secret"}},
            {**REPORT, "execution_id": 123},
            {**REPORT, "execution_id": "../123"},
            {**REPORT, "workflow_id": "unregistered"},
            {**REPORT, "status": "success"},
            {"workflow_id": "workflow-a"},
            [],
        ]:
            response = client.post(PATH, headers=AUTH, json=body)
            assert response.status_code == 422
            assert "customer data" not in response.text and "secret" not in response.text
        assert client.post(PATH, headers=AUTH, content="x" * 1025).status_code == 415
        headers = {**AUTH, "Content-Type": "application/json"}
        assert client.post(PATH, headers=headers, content="x" * 1025).status_code == 413
        assert (
            client.post(
                PATH,
                headers=headers,
                content='{"workflow_id":"a","workflow_id":"b","execution_id":"1"}',
            ).status_code
            == 422
        )
        assert client.get("/history/checks").json() == []


def test_ingest_auth_precedes_body_and_never_grants_operator_access(database_config, engine):
    config = configured(
        database_config, api_access_token=OPERATOR, api_allowed_hosts=["testserver"]
    )
    # Production rejects local storage, so the application is built with its valid
    # development config and only the isolated access-boundary mode is selected.
    app = create_app(config)
    config.environment = "production"
    with TestClient(app) as client:
        for headers in [
            {},
            {"Authorization": "Bearer " + OPERATOR},
            {**AUTH, "Origin": "https://example.com"},
            {**AUTH, "Host": "evil.example"},
        ]:
            assert client.post(PATH, headers=headers, content="x" * 2048).status_code in {400, 401}
        assert client.post(PATH, headers=AUTH, json=REPORT).status_code == 200
        assert client.get("/monitoring", headers=AUTH).status_code == 401
        assert client.get("/monitoring/n8n/reports", headers=AUTH).status_code == 401
        assert (
            client.post(
                "/monitoring/websites", headers=AUTH, json={"url": "https://example.com"}
            ).status_code
            == 401
        )
        assert client.get(PATH, headers=AUTH).status_code == 404
        full = {"Authorization": "Bearer " + OPERATOR}
        assert client.get("/monitoring/n8n/reports", headers=full).status_code == 200


def test_disabled_reports_and_unsafe_configuration_are_closed():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.post(PATH, headers=AUTH, json=REPORT).status_code == 404
        assert client.get("/monitoring/n8n/reports").json()["reports"] == []
    for changes in [
        {"n8n_events_token": None},
        {"n8n_events_workflow_ids": []},
        {"n8n_base_url": None},
        {"storage_mode": "disabled"},
        {"api_access_token": TOKEN},
    ]:
        with pytest.raises(ValidationError):
            configured(Settings(_env_file=None, storage_mode="local"), **changes)
    with pytest.raises(ValidationError):
        configured(Settings(_env_file=None, storage_mode="local"), n8n_mode="fixture")
    with pytest.raises(ValidationError):
        configured(Settings(_env_file=None, storage_mode="local"), n8n_events_token="short")


def test_storage_or_incident_failure_is_not_misreported(database_config, engine):
    with TestClient(create_app(configured(database_config))) as client:
        repository = client.app.state.history.repository
        with patch.object(repository, "record", side_effect=RuntimeError("private failure")):
            response = client.post(PATH, headers=AUTH, json=REPORT)
            assert response.status_code == 503 and "private failure" not in response.text
        with patch.object(
            repository, "ensure_incident", side_effect=RuntimeError("private failure")
        ):
            response = client.post(PATH, headers=AUTH, json=REPORT)
            assert response.status_code == 200
            assert response.json()["incident"]["status"] == "unavailable"
        assert len(client.get("/history/checks").json()) == 1
        assert client.get("/history/incidents").json() == []
        assert (
            client.post(PATH, headers=AUTH, json=REPORT).json()["incident"]["status"] == "created"
        )
        assert len(client.get("/history/checks").json()) == 1


def test_empty_reports_and_source_change_do_not_reuse_evidence(database_config, engine):
    config = configured(database_config)
    with TestClient(create_app(config)) as client:
        empty = asyncio.run(
            client.app.state.tool_registry.execute("read_n8n_failure_reports", "{}")
        )
        assert empty.data["status"] == "UNKNOWN"
        assert supports("workflow_failure", empty) is False
        assert client.post(PATH, headers=AUTH, json=REPORT).status_code == 200
    other = configured(database_config, n8n_base_url="https://another.example/api/v1/")
    with TestClient(create_app(other)) as client:
        assert client.get("/monitoring/n8n/reports").json()["reports"] == []
        assert len(client.get("/history/incidents").json()) == 1
        assert (
            client.post(PATH, headers=AUTH, json=REPORT).json()["incident"]["status"] == "created"
        )
        assert len(client.get("/history/checks").json()) == 2
