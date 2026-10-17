import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.fixtures import DEMO_QUESTION
from app.config import Settings
from app.db.capture import HistoryCapture, IncidentCapture
from app.db.repository import HistoryRepository
from app.db.service import HistoryService
from app.main import create_app
from app.tools.infrastructure_models import InfrastructureResult


def enabled_config(database_config, **options):
    return Settings(
        **{
            **database_config.model_dump(),
            "incidents_enabled": True,
            "environment": "test",
            "investigation_mode": "fixture",
            "n8n_mode": "fixture",
            "infrastructure_mode": "fixture",
            **options,
        },
        _env_file=None,
    )


def test_checks_automatically_open_and_reuse_incidents_with_unchanged_health_bodies(
    engine, database_config
):
    with TestClient(create_app(enabled_config(database_config))) as client:
        first = client.get("/n8n/executions/1001")
        second = client.get("/n8n/executions/1001")
        assert first.json()["execution"]["status"] == "UNHEALTHY"
        assert (
            first.headers["x-history-status"] == "saved"
            and first.headers["x-incident-status"] == "created"
        )
        assert second.headers["x-incident-status"] == "existing"
        identifier = first.headers["x-incident-id"]
        assert second.headers["x-incident-id"] == identifier
        incident = client.get("/history/incidents/" + identifier).json()
        assert incident["observation_count"] == 2 and incident["status"] == "OPEN"
        assert (
            incident["synthetic"]
            and incident["root_cause_verified"] is False
            and incident["verified"] is False
        )
        assert len(client.get(f"/history/incidents/{identifier}/observations").json()) == 2
        # Count is observations of the same execution, not two affected bookings.
        assert {
            row["payload"]["evidence"]["id"]
            for row in client.get(f"/history/incidents/{identifier}/observations").json()
        } == {"1001"}
        healthy = client.get("/n8n/executions/1002")
        assert healthy.headers["x-incident-status"] == "not_applicable"
        assert client.get("/history/incidents/" + identifier).json()["status"] == "OPEN"
        assert len(client.get("/history/incidents?synthetic=true").json()) == 1
        assert client.get("/history/incidents?synthetic=false").json() == []


def test_investigation_reports_actual_created_and_existing_incident_ids(engine, database_config):
    with TestClient(create_app(enabled_config(database_config))) as client:
        first = client.post("/investigations", json={"question": DEMO_QUESTION}).json()
        second = client.post("/investigations", json={"question": DEMO_QUESTION}).json()
        assert first["status"] == second["status"] == "COMPLETED"
        assert first["incident_created"] is True and second["incident_created"] is False
        assert len(first["incident_ids"]) == 1 and first["incident_ids"] == second["incident_ids"]
        assert first["evidence"][1]["result"]["history"]["incident"]["status"] == "created"
        assert first["root_cause_verified"] is False and first["remediation_executed"] is False
        assert client.get("/agent").json()["automatic_incidents"] is True
        assert client.get("/storage").json()["automatic_incidents"] is True
        assert client.get("/tools").json()["policy"]["automatic_incidents"] is True
        assert client.get("/history/incidents").json()[0]["observation_count"] == 2


def test_parallel_check_requests_do_not_duplicate_incidents(engine, database_config):
    with TestClient(create_app(enabled_config(database_config))) as client:
        with ThreadPoolExecutor(max_workers=8) as executor:
            responses = list(executor.map(lambda _: client.get("/n8n/executions/1001"), range(8)))
        assert all(
            response.status_code == 200 and response.headers["x-history-status"] == "saved"
            for response in responses
        )
        assert (
            sum(response.headers["x-incident-status"] == "created" for response in responses) == 1
        )
        assert len({response.headers["x-incident-id"] for response in responses}) == 1
        assert client.get("/history/incidents").json()[0]["observation_count"] == 8


@pytest.mark.parametrize("status", ["HEALTHY", "DEGRADED", "UNKNOWN", "CHECK_FAILED"])
def test_nonfailure_checks_never_create_incidents(engine, database_config, status):
    async def check(_):
        return InfrastructureResult(
            component="vercel-deployment",
            check_type="deployment",
            status=status,
            summary="test",
            synthetic=True,
        )

    with TestClient(
        create_app(enabled_config(database_config), infrastructure_service=Mock(check=check))
    ) as client:
        response = client.post("/checks/infrastructure/vercel-deployment")
        assert (
            response.json()["status"] == status
            and response.headers["x-incident-status"] == "not_applicable"
        )
        assert "x-incident-id" not in response.headers
        assert client.get("/history/incidents").json() == []


def test_incident_transaction_failure_does_not_discard_saved_check(
    engine, database_config, monkeypatch, caplog
):
    app = create_app(enabled_config(database_config))

    def fail(*_):
        raise RuntimeError("SECRET_SQL_CONNECTION")

    monkeypatch.setattr(app.state.history.repository, "ensure_incident", fail)
    with TestClient(app) as client:
        response = client.get("/n8n/executions/1001")
        assert response.json()["execution"]["status"] == "UNHEALTHY"
        assert (
            response.headers["x-history-status"] == "saved"
            and response.headers["x-incident-status"] == "unavailable"
        )
        assert client.get("/history/checks/" + response.headers["x-check-id"]).status_code == 200
        assert client.get("/history/incidents").json() == []
        assert client.get("/storage").json()["state"] == "ready"
        report = client.post("/investigations", json={"question": DEMO_QUESTION}).json()
        assert (
            report["status"] == "COMPLETED"
            and report["incident_created"] is False
            and report["incident_ids"] == []
        )
        assert (
            "SECRET_SQL_CONNECTION" not in str(report)
            and "SECRET_SQL_CONNECTION" not in caplog.text
        )


def test_incident_persistence_does_not_depend_on_valid_model_conclusion(engine, database_config):
    import json

    import httpx

    from app.agent.client import NebiusClient

    settings = enabled_config(database_config, nebius_api_key="test-key")
    turns = iter(
        [
            {
                "id": "first",
                "model": settings.nebius_model,
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call",
                                    "type": "function",
                                    "function": {
                                        "name": "get_n8n_execution",
                                        "arguments": '{"execution_id":"1001"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
            {
                "id": "final",
                "model": settings.nebius_model,
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "hypothesis": "credential_expired",
                                    "evidence_ids": ["e1"],
                                    "next_steps": ["inspect_execution"],
                                }
                            ),
                        },
                    }
                ],
            },
        ]
    )

    def handler(request):
        return httpx.Response(
            200,
            json={"data": [{"id": settings.nebius_model}]}
            if request.method == "GET"
            else next(turns),
        )

    with TestClient(
        create_app(
            settings,
            agent_client_factory=lambda: NebiusClient(
                settings, transport=httpx.MockTransport(handler)
            ),
        )
    ) as client:
        report = client.post("/investigations", json={"question": DEMO_QUESTION}).json()
        assert report["status"] == "INCOMPLETE" and report["reason"] == "invalid_final"
        assert report["incident_created"] is True and len(report["incident_ids"]) == 1
        assert len(client.get("/history/incidents").json()) == 1
        assert (
            client.get(f"/history/incidents/{report['incident_ids'][0]}/assessments").json() == []
        )
        assert report["incident_assessment"]["status"] == "not_applicable"


def test_incident_creation_is_opt_in_and_missing_storage_is_explicit():
    with TestClient(
        create_app(Settings(_env_file=None, environment="test", n8n_mode="fixture"))
    ) as client:
        assert client.get("/n8n/executions/1001").headers["x-incident-status"] == "disabled"
    with TestClient(
        create_app(
            Settings(
                _env_file=None,
                environment="test",
                incidents_enabled=True,
                storage_mode="disabled",
                n8n_mode="fixture",
            )
        )
    ) as client:
        response = client.get("/n8n/executions/1001")
        assert (
            response.headers["x-history-status"] == "disabled"
            and response.headers["x-incident-status"] == "unavailable"
        )
        assert response.json()["execution"]["status"] == "UNHEALTHY"
        assert client.get("/n8n/executions/1002").headers["x-incident-status"] == "not_applicable"


def test_cancellation_and_close_drain_the_entire_capture_worker(
    engine, database_config, monkeypatch
):
    settings = enabled_config(database_config)
    history = HistoryService(settings)
    entered, release = threading.Event(), threading.Event()
    original = history.repository.ensure_incident

    def delayed(identifier):
        entered.set()
        if not release.wait(3):
            raise RuntimeError("test worker was not released")
        return original(identifier)

    monkeypatch.setattr(history.repository, "ensure_incident", delayed)

    async def run():
        capture = asyncio.create_task(
            history.capture(
                InfrastructureResult(
                    component="vercel-deployment",
                    check_type="deployment",
                    status="UNHEALTHY",
                    summary="fixture",
                    synthetic=True,
                ),
                "fixture",
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            capture.cancel()
            with pytest.raises(asyncio.CancelledError):
                await capture
            closing = asyncio.create_task(history.close())
            await asyncio.sleep(0)
            assert not closing.done()
        finally:
            release.set()
            await history.close()
        await closing

    asyncio.run(run())
    assert len(HistoryRepository(engine).incidents()) == 1


def test_read_only_incident_routes_are_bounded_and_no_write_or_resolution_route_exists(
    engine, database_config
):
    with TestClient(create_app(enabled_config(database_config))) as client:
        identifier = client.get("/n8n/executions/1001").headers["x-incident-id"]
        for query in ["limit=0", "limit=101", "offset=-1", "offset=10001"]:
            assert (
                client.get(f"/history/incidents/{identifier}/observations?{query}").status_code
                == 422
            )
        assert client.get("/history/incidents/" + str(uuid4())).status_code == 404
        assert client.get(f"/history/incidents/{uuid4()}/observations").status_code == 404
        assert client.get(f"/history/incidents/{uuid4()}/assessments").status_code == 404
        assert client.post("/history/incidents", json={"status": "RESOLVED"}).status_code == 405
        assert (
            client.patch(
                "/history/incidents/" + identifier, json={"status": "RESOLVED"}
            ).status_code
            == 405
        )
        assert client.delete("/history/incidents/" + identifier).status_code == 405
        assert client.post("/incidents", json={}).status_code == 404


def test_production_incident_creation_and_reads_are_disabled():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", incidents_enabled=True)
    with TestClient(create_app(Settings(_env_file=None, environment="production"))) as client:
        assert client.get("/history/incidents/" + str(uuid4())).status_code == 404
        assert client.get(f"/history/incidents/{uuid4()}/observations").status_code == 404


@pytest.mark.parametrize(
    "capture",
    [
        {"status": "created"},
        {"status": "unavailable", "incident_id": str(uuid4())},
        {"status": "existing", "incident_id": "bad"},
    ],
)
def test_incident_outcomes_cannot_claim_unconfirmed_ids(capture):
    with pytest.raises(ValidationError):
        IncidentCapture.model_validate(capture)


def test_unpersisted_checks_cannot_claim_incident_creation():
    with pytest.raises(ValidationError):
        HistoryCapture(
            status="unavailable",
            incident=IncidentCapture(status="created", incident_id=str(uuid4())),
        )
