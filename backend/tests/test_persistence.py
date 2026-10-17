from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import inspect, update

from app.actions.models import RetryAction
from app.db.database import create_storage_engine
from app.db.migrate import HEAD, current_revision, downgrade, upgrade
from app.db.models import (
    Incident,
    IncidentAssessment,
    IncidentObservation,
    MonitoredService,
    StoredCheck,
)
from app.db.repository import HistoryRepository, StorageError
from app.db.snapshots import Snapshot, snapshot_for
from app.tools.infrastructure_models import InfrastructureResult


def observation(*, status="UNHEALTHY", synthetic=True, source="fixture", at=None):
    result = InfrastructureResult(
        component="vercel-deployment",
        check_type="deployment",
        status=status,
        synthetic=synthetic,
        summary="Provider-reported deployment state",
        checked_at=at or datetime.now(UTC),
        evidence={"ready_state": "ERROR" if status == "UNHEALTHY" else "READY"},
    )
    return snapshot_for(result, source)


def test_migration_is_idempotent_and_supports_rollback_then_upgrade(engine):
    assert current_revision(engine) == HEAD
    upgrade(engine)
    schema = "reliability" if engine.dialect.name == "postgresql" else None
    inspector = inspect(engine)
    assert {
        "monitored_services",
        "checks",
        "incidents",
        "incident_observations",
        "incident_assessments",
        "retry_actions",
        "ra_schema_version",
    } <= set(inspector.get_table_names(schema=schema))
    assert {row["name"] for row in inspector.get_indexes("checks", schema=schema)} >= {
        "ix_checks_created",
        "ix_checks_service_observed",
    }
    assert len(inspector.get_foreign_keys("incidents", schema=schema)) == 3
    downgrade(engine, "base")
    assert current_revision(engine) is None
    upgrade(engine)
    assert current_revision(engine) == HEAD


def test_schema_and_orm_columns_match(engine):
    schema = "reliability" if engine.dialect.name == "postgresql" else None
    inspector = inspect(engine)
    for model in (
        MonitoredService,
        StoredCheck,
        Incident,
        IncidentObservation,
        IncidentAssessment,
        RetryAction,
    ):
        assert {
            column["name"] for column in inspector.get_columns(model.__tablename__, schema=schema)
        } == set(model.__table__.columns.keys())


def test_check_and_service_survive_a_new_engine(repository, database_config):
    snapshot = observation()
    identifier = repository.record(snapshot)
    repository.engine.dispose()
    reopened = create_storage_engine(database_config)
    try:
        stored = HistoryRepository(reopened).check(identifier)
        assert stored["status"] == "UNHEALTHY" and stored["service_id"] == snapshot.service_id
        assert stored["payload"] == snapshot.payload
        assert stored["observed_at"].utcoffset() == timedelta(0)
    finally:
        reopened.dispose()


def test_all_check_states_are_preserved_without_collapsing_unknowns(repository):
    for status in ("HEALTHY", "UNHEALTHY", "DEGRADED", "UNKNOWN", "CHECK_FAILED"):
        identifier = repository.record(observation(status=status))
        assert repository.check(identifier)["status"] == status
    assert len(repository.services()) == 1
    assert repository.incidents() == []


def test_synthetic_live_and_changed_targets_do_not_share_services(repository):
    for value in (
        observation(),
        observation(synthetic=False),
        observation(source="changed-target"),
    ):
        repository.record(value)
    assert len(repository.services()) == 3
    assert len(repository.checks(synthetic=False)) == 1
    assert len(repository.checks(synthetic=True)) == 2


def test_pagination_filters_and_detail_ids(repository):
    values = [repository.record(observation(status="HEALTHY")) for _ in range(5)]
    repository.record(observation(status="UNHEALTHY", source="other"))
    assert len(repository.checks(limit=2)) == 2
    assert len(repository.checks(limit=2, offset=2)) == 2
    assert len(repository.checks(status="HEALTHY")) == 5
    assert len(repository.checks(service_id=observation().service_id)) == 5
    assert repository.check(str(uuid4())) is None
    assert all(repository.check(identifier)["id"] == identifier for identifier in values)


def test_timestamp_is_normalized_to_utc(repository):
    at = datetime(2026, 10, 17, 15, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    identifier = repository.record(observation(at=at))
    assert repository.check(identifier)["observed_at"] == datetime(2026, 10, 17, 9, 30, tzinfo=UTC)


def test_concurrent_first_checks_register_one_service(repository):
    value = observation()
    with ThreadPoolExecutor(max_workers=4) as executor:
        identifiers = list(executor.map(lambda _: repository.record(value), range(8)))
    assert len(set(identifiers)) == 8
    assert len(repository.services()) == 1 and len(repository.checks()) == 8


def test_transaction_rolls_back_all_partial_work(repository):
    with pytest.raises(RuntimeError, match="abort"):
        with repository.transaction() as session:
            session.add(
                MonitoredService(
                    id=str(uuid4()), category="website", component="demo", synthetic=True
                )
            )
            session.flush()
            raise RuntimeError("abort")
    assert repository.services() == []


def test_foreign_keys_and_invalid_status_are_enforced(repository):
    with pytest.raises(StorageError):
        with repository.transaction() as session:
            session.add(
                StoredCheck(
                    service_id=str(uuid4()),
                    kind="http",
                    status="HEALTHY",
                    observed_at=datetime.now(UTC),
                    payload={},
                )
            )
    identifier = repository.record(observation())
    with pytest.raises(StorageError):
        with repository.transaction() as session:
            session.execute(
                update(StoredCheck).where(StoredCheck.id == identifier).values(status="SUCCESS")
            )
    assert repository.check(identifier)["status"] == "UNHEALTHY"


def test_incident_links_to_failure_and_survives_restart(repository, database_config):
    identifier = repository.record(observation())
    incident = repository.create_open_incident(identifier)
    assert incident["status"] == "OPEN" and incident["verified"] is False
    assert repository.create_open_incident(identifier)["id"] == incident["id"]
    reopened = create_storage_engine(database_config)
    try:
        assert HistoryRepository(reopened).incidents()[0]["id"] == incident["id"]
    finally:
        reopened.dispose()


@pytest.mark.parametrize("status", ["HEALTHY", "UNKNOWN", "CHECK_FAILED", "DEGRADED"])
def test_incident_cannot_be_created_from_nonfailure(repository, status):
    identifier = repository.record(observation(status=status))
    with pytest.raises(StorageError, match="incident_requires_unhealthy_evidence"):
        repository.create_open_incident(identifier)
    assert repository.incidents() == []


def test_incident_cannot_cross_service_boundary(repository):
    first = repository.record(observation())
    second = repository.record(observation(source="other"))
    second_service = repository.check(second)["service_id"]
    with pytest.raises(StorageError):
        with repository.transaction() as session:
            session.add(
                Incident(
                    service_id=second_service,
                    detected_check_id=first,
                    kind="deployment",
                    status="OPEN",
                    severity="high",
                )
            )
    assert repository.incidents() == []


def test_resolution_is_blocked_at_the_database_layer(repository):
    incident = repository.create_open_incident(repository.record(observation()))
    with pytest.raises(StorageError):
        with repository.transaction() as session:
            session.execute(
                update(Incident).where(Incident.id == incident["id"]).values(status="RESOLVED")
            )
    assert repository.incidents()[0]["status"] == "OPEN"


def test_api_credentials_and_source_are_not_stored(repository):
    marker = "SYNTHETIC_SECRET_DO_NOT_STORE"
    result = InfrastructureResult(
        component="vercel-events",
        check_type="events",
        status="UNKNOWN",
        summary=marker,
        synthetic=True,
        evidence={"events": [{"type": "stderr", "created_ms": 123, "text": marker}], "raw": marker},
    )
    identifier = repository.record(
        snapshot_for(result, "postgresql://user:" + marker + "@db.example/x")
    )
    assert marker not in str(repository.check(identifier))
    assert marker not in str(repository.services())


@pytest.mark.parametrize("limit,offset", [(0, 0), (101, 0), (True, 0), (1, -1), (1, 10001)])
def test_unbounded_pagination_is_rejected(repository, limit, offset):
    with pytest.raises(StorageError, match="invalid_pagination"):
        repository.checks(limit=limit, offset=offset)


def test_invalid_identifiers_are_rejected_before_query(repository):
    with pytest.raises(StorageError, match="invalid_identifier"):
        repository.check("'; DROP TABLE checks; --")


def test_invalid_observation_is_rejected_before_write(repository):
    value = observation().model_dump()
    value["observed_at"] = datetime(2026, 10, 17)
    with pytest.raises(ValueError):
        Snapshot.model_validate(value)
    value["observed_at"] = datetime.now(UTC)
    value["payload"] = {"evidence": "x" * 65537}
    with pytest.raises(ValueError):
        Snapshot.model_validate(value)
    assert repository.services() == []
