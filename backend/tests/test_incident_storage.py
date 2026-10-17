from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import MetaData, Table, func, inspect, select, update

from app.db.database import create_storage_engine
from app.db.migrate import HEAD, current_revision, downgrade, upgrade
from app.db.models import Incident, IncidentObservation, StoredCheck
from app.db.repository import HistoryRepository, StorageError
from app.db.snapshots import Snapshot, snapshot_for
from app.tools.models import CheckResult


def observation(
    *, status="UNHEALTHY", kind="http", source="https://example.com/", synthetic=False, at=None
):
    snapshot = snapshot_for(
        CheckResult(
            component="homepage",
            check_type=kind,
            status=status,
            summary="Not stored",
            checked_at=at or datetime.now(UTC),
            evidence={"http_status": 503 if status == "UNHEALTHY" else 200},
        ),
        source,
    )
    return Snapshot.model_validate({**snapshot.model_dump(), "synthetic": synthetic})


def test_repeated_failures_share_one_incident_and_replay_is_idempotent(repository):
    first, second = [repository.record(observation()) for _ in range(2)]
    opened, created = repository.ensure_incident(first)
    reused, created_again = repository.ensure_incident(second)
    replay, created_replay = repository.ensure_incident(first)
    assert created and not created_again and not created_replay
    assert opened["id"] == reused["id"] == replay["id"]
    assert replay["detected_check_id"] == first and replay["observation_count"] == 2
    assert len(repository.incidents()) == 1
    assert {row["id"] for row in repository.incident_observations(opened["id"])} == {first, second}


def test_concurrent_same_check_creates_one_incident_and_one_link(repository):
    for iteration in range(3):
        identifier = repository.record(observation(source=f"https://example.com/{iteration}"))
        barrier = Barrier(8)

        def detect(check_id, barrier=barrier):
            barrier.wait(timeout=10)
            return repository.ensure_incident(check_id)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(detect, [identifier] * 16))
        assert sum(created for _, created in results) == 1
        assert len({row["id"] for row, _ in results}) == 1
        assert repository.incident(results[0][0]["id"])["observation_count"] == 1
    assert len(repository.incidents()) == 3


def test_concurrent_distinct_failed_observations_do_not_create_incident_storm(repository):
    identifiers = [repository.record(observation()) for _ in range(16)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(repository.ensure_incident, identifiers))
    assert sum(created for _, created in results) == 1
    assert len(repository.incidents()) == 1
    assert repository.incidents()[0]["observation_count"] == 16
    assert len(repository.incident_observations(results[0][0]["id"])) == 16


def test_service_kind_source_and_fixture_boundaries_are_distinct(repository):
    values = [
        observation(),
        observation(kind="dns"),
        observation(source="https://other.example/"),
        observation(synthetic=True),
    ]
    incidents = [repository.ensure_incident(repository.record(value))[0] for value in values]
    assert len({row["id"] for row in incidents}) == 4
    assert len(repository.incidents(synthetic=True)) == 1
    assert len(repository.incidents(synthetic=False)) == 3


def test_new_failures_do_not_change_investigating_state_or_first_evidence(repository):
    first = repository.record(observation())
    incident = repository.create_open_incident(first, severity="warning")
    with repository.transaction() as session:
        session.execute(
            update(Incident).where(Incident.id == incident["id"]).values(status="INVESTIGATING")
        )
    later, created = repository.ensure_incident(repository.record(observation()))
    assert not created and later["status"] == "INVESTIGATING"
    assert later["severity"] == "warning" and later["detected_check_id"] == first


def test_out_of_order_observations_keep_true_first_and_last_times(repository):
    current = datetime.now(UTC)
    first = repository.create_open_incident(repository.record(observation(at=current)))
    repository.ensure_incident(repository.record(observation(at=current - timedelta(hours=1))))
    repository.ensure_incident(repository.record(observation(at=current + timedelta(hours=1))))
    detail = repository.incident(first["id"])
    assert detail["first_observed_at"] == current - timedelta(hours=1)
    assert detail["last_observed_at"] == current + timedelta(hours=1)
    assert detail["observation_count"] == 3


def test_incident_links_survive_engine_restart(repository, database_config):
    identifier = repository.record(observation())
    incident = repository.create_open_incident(identifier)
    reopened = create_storage_engine(database_config)
    try:
        other = HistoryRepository(reopened)
        assert other.incident(incident["id"])["observation_count"] == 1
        assert other.ensure_incident(identifier)[1] is False
        assert other.incident_observations(incident["id"])[0]["id"] == identifier
    finally:
        reopened.dispose()


@pytest.mark.parametrize("status", ["HEALTHY", "DEGRADED", "UNKNOWN", "CHECK_FAILED"])
def test_no_incident_or_evidence_link_for_nonfailure(repository, status):
    with pytest.raises(StorageError, match="incident_requires_unhealthy_evidence"):
        repository.ensure_incident(repository.record(observation(status=status)))
    assert repository.incidents() == []
    with repository.transaction() as session:
        assert session.scalar(select(func.count()).select_from(IncidentObservation)) == 0


@pytest.mark.parametrize("fault", ["healthy", "wrong_kind", "wrong_service", "wrong_status"])
def test_database_enforces_unhealthy_initial_detection_even_for_direct_orm_writes(
    repository, fault
):
    failed = repository.record(observation())
    check = repository.check(failed)
    target = repository.record(observation(status="HEALTHY")) if fault == "healthy" else failed
    with pytest.raises(StorageError):
        with repository.transaction() as session:
            session.add(
                Incident(
                    service_id=str(uuid4()) if fault == "wrong_service" else check["service_id"],
                    detected_check_id=target,
                    kind="dns" if fault == "wrong_kind" else "http",
                    evidence_status="HEALTHY" if fault == "wrong_status" else "UNHEALTHY",
                    status="OPEN",
                    severity="high",
                )
            )
    assert repository.incidents() == []


@pytest.mark.parametrize("fault", ["healthy", "wrong_kind", "wrong_service", "wrong_status"])
def test_database_rejects_unrelated_or_healthy_incident_observations(repository, fault):
    initial = repository.record(observation())
    incident = repository.create_open_incident(initial)
    other = repository.record(
        observation(
            status="HEALTHY" if fault == "healthy" else "UNHEALTHY",
            kind="dns" if fault == "wrong_kind" else "http",
            source="changed" if fault == "wrong_service" else "https://example.com/",
        )
    )
    with pytest.raises(StorageError):
        with repository.transaction() as session:
            session.add(
                IncidentObservation(
                    incident_id=incident["id"],
                    check_id=other,
                    service_id=incident["service_id"],
                    kind="http",
                    check_status="HEALTHY" if fault == "wrong_status" else "UNHEALTHY",
                )
            )
    assert repository.incident(incident["id"])["observation_count"] == 1


def test_failed_link_transaction_does_not_leave_an_extra_incident(repository, monkeypatch):
    from sqlalchemy import event

    identifier = repository.record(observation())

    def reject_link(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO") and "incident_observations" in statement:
            raise RuntimeError("synthetic failure")

    event.listen(repository.engine, "before_cursor_execute", reject_link)
    try:
        with pytest.raises(RuntimeError, match="synthetic failure"):
            repository.ensure_incident(identifier)
    finally:
        event.remove(repository.engine, "before_cursor_execute", reject_link)
    assert repository.incidents() == [] and repository.check(identifier) is not None


def test_active_unique_index_and_resolution_guard_are_enforced(repository):
    first, second = [repository.record(observation()) for _ in range(2)]
    incident = repository.create_open_incident(first)
    with pytest.raises(StorageError):
        with repository.transaction() as session:
            session.add(
                Incident(
                    service_id=incident["service_id"],
                    detected_check_id=second,
                    kind="http",
                    status="INVESTIGATING",
                    severity="high",
                )
            )
    with pytest.raises(StorageError):
        with repository.transaction() as session:
            session.execute(
                update(Incident).where(Incident.id == incident["id"]).values(status="RESOLVED")
            )
    with pytest.raises(StorageError):
        with repository.transaction() as session:
            session.execute(
                update(StoredCheck).where(StoredCheck.id == first).values(status="HEALTHY")
            )
    assert repository.incident(incident["id"])["status"] == "OPEN"


def legacy_incidents(engine, check_ids):
    downgrade(engine, "0001_history")
    schema = "reliability" if engine.dialect.name == "postgresql" else None
    legacy = Table("incidents", MetaData(), schema=schema, autoload_with=engine)
    identifiers = []
    with engine.begin() as connection:
        for check_id in check_ids:
            service_id = connection.scalar(
                select(StoredCheck.service_id).where(StoredCheck.id == check_id)
            )
            identifier = str(uuid4())
            connection.execute(
                legacy.insert().values(
                    id=identifier,
                    service_id=service_id,
                    detected_check_id=check_id,
                    status="OPEN",
                    severity="high",
                    created_at=datetime.now(UTC),
                )
            )
            identifiers.append(identifier)
    return identifiers


def test_migration_preserves_legacy_incident_ids_and_backfills_initial_evidence(repository, engine):
    identifier = repository.record(observation())
    old_id = legacy_incidents(engine, [identifier])[0]
    upgrade(engine)
    incident = repository.incident(old_id)
    assert current_revision(engine) == HEAD and incident["kind"] == "http"
    assert incident["detected_check_id"] == identifier and incident["observation_count"] == 1
    assert repository.ensure_incident(identifier)[0]["id"] == old_id


@pytest.mark.parametrize("case", ["duplicate", "healthy"])
def test_unsafe_legacy_migration_stops_before_ddl_without_deleting_history(
    repository, engine, case
):
    ids = [
        repository.record(observation(status="HEALTHY" if case == "healthy" else "UNHEALTHY"))
        for _ in range(2 if case == "duplicate" else 1)
    ]
    old_ids = legacy_incidents(engine, ids)
    with pytest.raises(ValueError, match="nonduplicate unresolved history"):
        upgrade(engine)
    assert current_revision(engine) == "0001_history"
    schema = "reliability" if engine.dialect.name == "postgresql" else None
    inspector = inspect(engine)
    assert "kind" not in {
        column["name"] for column in inspector.get_columns("incidents", schema=schema)
    }
    assert "incident_observations" not in inspector.get_table_names(schema=schema)
    legacy = Table("incidents", MetaData(), schema=schema, autoload_with=engine)
    with engine.connect() as connection:
        assert set(connection.scalars(select(legacy.c.id))) == set(old_ids)


def test_incident_evidence_pagination_and_missing_ids(repository):
    incident_id = None
    for _ in range(4):
        incident_id = repository.create_open_incident(repository.record(observation()))["id"]
    assert len(repository.incident_observations(incident_id, limit=2, offset=2)) == 2
    assert repository.incident(str(uuid4())) is None
    assert repository.incident_observations(str(uuid4())) == []
    for limit, offset in [(0, 0), (101, 0), (True, 0), (1, -1), (1, 10001)]:
        with pytest.raises(StorageError, match="invalid_pagination"):
            repository.incident_observations(incident_id, limit=limit, offset=offset)
