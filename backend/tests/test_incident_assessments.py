import asyncio
import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.fixtures import DEMO_QUESTION
from app.config import Settings
from app.db.assessment import AssessmentCapture, AssessmentDraft
from app.db.models import IncidentAssessment
from app.db.repository import HistoryRepository, StorageError
from app.db.snapshots import snapshot_for
from app.main import create_app
from app.tools.models import CheckResult


def config(database_config):
    return Settings(
        **{
            **database_config.model_dump(),
            "environment": "test",
            "incidents_enabled": True,
            "investigation_mode": "fixture",
            "n8n_mode": "fixture",
            "infrastructure_mode": "fixture",
        },
        _env_file=None,
    )


def failure(repository, *, synthetic=True):
    identifier = repository.record(
        snapshot_for(
            CheckResult(component="website", check_type="http", status="UNHEALTHY", summary="test"),
            "https://example.com/",
        ).model_copy(update={"synthetic": synthetic})
    )
    incident, _ = repository.ensure_incident(identifier)
    return identifier, incident["id"]


def draft(identifier, **kwargs):
    return AssessmentDraft(
        **{
            "check_id": identifier,
            "hypothesis": "website_failure",
            "recommended_steps": ["inspect_website"],
            "inference_source": "scripted_fixture",
            **kwargs,
        }
    )


def test_supported_assessment_is_durable_and_replay_does_not_rewrite_it(repository):
    identifier, incident_id = failure(repository)
    assert repository.save_assessments([draft(identifier)]) == [identifier]
    repository.save_assessments([draft(identifier, recommended_steps=["collect_more_evidence"])])
    rows = HistoryRepository(repository.engine).incident_assessments(incident_id)
    assert len(rows) == 1 and rows[0]["check_id"] == identifier
    assert rows[0]["hypothesis"] == "website_failure"
    assert rows[0]["recommended_steps"] == ["inspect_website"]
    assert rows[0]["root_cause"] is None and rows[0]["root_cause_verified"] is False


@pytest.mark.parametrize("fault", ["unsupported", "no_link", "provenance"])
def test_assessment_requires_supporting_linked_evidence_and_correct_provenance(repository, fault):
    identifier, incident_id = failure(repository, synthetic=fault != "provenance")
    value = draft(
        identifier, **({"hypothesis": "authentication_rejection"} if fault == "unsupported" else {})
    )
    if fault == "no_link":
        value = draft(str(uuid4()))
    with pytest.raises(StorageError):
        repository.save_assessments([value])
    assert repository.incident_assessments(incident_id) == []


def test_assessment_batch_failure_rolls_back_all_diagnoses(repository):
    identifier, incident_id = failure(repository)
    with pytest.raises(StorageError):
        repository.save_assessments([draft(identifier), draft(str(uuid4()))])
    assert repository.incident_assessments(incident_id) == []


@pytest.mark.parametrize("fault", ["root_cause", "hypothesis", "missing_evidence"])
def test_assessment_database_guards_reject_fabricated_cause_and_missing_evidence(repository, fault):
    identifier, incident_id = failure(repository)
    with pytest.raises(StorageError):
        with repository.transaction() as session:
            session.add(
                IncidentAssessment(
                    check_id=str(uuid4()) if fault == "missing_evidence" else identifier,
                    hypothesis="expired_credential" if fault == "hypothesis" else "website_failure",
                    recommended_steps=["inspect_website"],
                    inference_source="scripted_fixture",
                    root_cause="credential_expired" if fault == "root_cause" else None,
                )
            )
    assert repository.incident_assessments(incident_id) == []


def test_completed_investigation_persists_only_cited_supported_failure_assessments(
    engine, database_config
):
    with TestClient(create_app(config(database_config))) as client:
        report = client.post("/investigations", json={"question": DEMO_QUESTION}).json()
        assert report["incident_assessment"]["status"] == "saved"
        assert len(report["incident_assessment"]["check_ids"]) == 1
        incident_id = report["incident_ids"][0]
        path = f"/history/incidents/{incident_id}/assessments"
        rows = client.get(path).json()
        assert len(rows) == 1 and rows[0]["hypothesis"] == "authentication_rejection"
        assert rows[0]["check_id"] in report["incident_assessment"]["check_ids"]
        assert rows[0]["inference_source"] == "scripted_fixture"
        assert rows[0]["recommended_steps"] == report["next_steps"]
        assert rows[0]["root_cause"] is None and report["root_cause_verified"] is False
        assert client.get(path + "?limit=101").status_code == 422
        assert client.get(f"/history/incidents/{uuid4()}/assessments").status_code == 404
        assert client.post(path).status_code == 405
    with TestClient(create_app(config(database_config))) as client:
        assert client.get(path).json() == rows


def test_assessment_save_failure_preserves_incident_check_and_model_conclusion(
    engine, database_config, monkeypatch, caplog
):
    app = create_app(config(database_config))

    def fail(_):
        raise RuntimeError("PRIVATE_DATABASE_SECRET")

    monkeypatch.setattr(app.state.history.repository, "save_assessments", fail)
    with TestClient(app) as client:
        report = client.post("/investigations", json={"question": DEMO_QUESTION}).json()
        assert report["status"] == "COMPLETED" and report["incident_created"] is True
        assert report["incident_assessment"] == {"status": "unavailable", "check_ids": []}
        assert len(client.get("/history/checks").json()) == 3
        assert len(client.get("/history/incidents").json()) == 1
        assert (
            client.get(f"/history/incidents/{report['incident_ids'][0]}/assessments").json() == []
        )
    assert "PRIVATE_DATABASE_SECRET" not in caplog.text and "PRIVATE_DATABASE_SECRET" not in str(
        report
    )


def test_cancelled_investigation_drains_pending_assessment_before_releasing_slots(
    engine, database_config, monkeypatch
):
    app = create_app(config(database_config))
    entered, release = threading.Event(), threading.Event()
    original = app.state.history.repository.save_assessments

    def delayed(values):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("test worker was not released")
        return original(values)

    monkeypatch.setattr(app.state.history.repository, "save_assessments", delayed)

    async def run():
        caller = asyncio.create_task(app.state.investigator.investigate(DEMO_QUESTION))
        try:
            assert await asyncio.to_thread(entered.wait, 4)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
            assert (await app.state.tool_registry.execute("check_postgres", "{}")).reason == "busy"
            closing = asyncio.create_task(app.state.investigator.close())
            await asyncio.sleep(0)
            assert not closing.done()
        finally:
            release.set()
            await app.state.investigator.close()
            await app.state.tool_registry.close()
            await app.state.history.close()

    asyncio.run(run())
    repository = HistoryRepository(engine)
    assert len(repository.incident_assessments(repository.incidents()[0]["id"])) == 1


@pytest.mark.parametrize(
    "values",
    [
        {"root_cause": "credential_expired"},
        {"root_cause_verified": True},
        {"recommended_steps": ["run_shell"]},
        {"inference_source": "unlabeled_model"},
        {"hypothesis": "credential_expired"},
    ],
)
def test_assessment_schema_rejects_unsupported_claims_and_actions(values):
    with pytest.raises(ValidationError):
        draft(str(uuid4()), **values)


def test_assessment_capture_cannot_claim_unconfirmed_saves():
    for value in [
        {"status": "saved"},
        {"status": "unavailable", "check_ids": [str(uuid4())]},
    ]:
        with pytest.raises(ValidationError):
            AssessmentCapture.model_validate(value)
