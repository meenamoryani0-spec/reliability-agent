"""One transaction/session per operation; no arbitrary query or delete API."""

from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.models import Incident, MonitoredService, StoredCheck, now
from app.db.snapshots import Snapshot


class StorageError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def valid_id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise StorageError("invalid_identifier") from None


def page_bounds(limit, offset):
    if (
        type(limit) is not int
        or not 1 <= limit <= 100
        or type(offset) is not int
        or not 0 <= offset <= 10000
    ):
        raise StorageError("invalid_pagination")


def service_dict(row):
    return {
        "id": row.id,
        "category": row.category,
        "component": row.component,
        "synthetic": row.synthetic,
        "created_at": row.created_at,
    }


def check_dict(row, service):
    return {
        "id": row.id,
        "service_id": row.service_id,
        "category": service.category,
        "component": service.component,
        "synthetic": service.synthetic,
        "kind": row.kind,
        "status": row.status,
        "observed_at": row.observed_at,
        "created_at": row.created_at,
        "payload": row.payload,
    }


def incident_dict(row, service):
    return {
        "id": row.id,
        "service_id": row.service_id,
        "detected_check_id": row.detected_check_id,
        "status": row.status,
        "severity": row.severity,
        "created_at": row.created_at,
        "synthetic": service.synthetic,
        "root_cause_verified": False,
        "verified": False,
    }


class HistoryRepository:
    def __init__(self, engine):
        self.engine = engine
        self.sessions = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def transaction(self):
        try:
            with self.sessions.begin() as session:
                yield session
        except SQLAlchemyError:
            raise StorageError("storage_unavailable") from None

    def record(self, value: Snapshot):
        # Revalidate at the repository boundary before any transaction begins.
        snapshot = Snapshot.model_validate(value.model_dump())
        with self.transaction() as session:
            insert = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
            session.execute(
                insert(MonitoredService)
                .values(
                    id=snapshot.service_id,
                    category=snapshot.category,
                    component=snapshot.component,
                    synthetic=snapshot.synthetic,
                    created_at=now(),
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            check = StoredCheck(
                service_id=snapshot.service_id,
                kind=snapshot.kind,
                status=snapshot.status,
                observed_at=snapshot.observed_at,
                payload=snapshot.payload,
            )
            session.add(check)
            session.flush()
            return check.id

    def services(self, *, limit=25, offset=0, synthetic=None):
        page_bounds(limit, offset)
        with self.transaction() as session:
            query = select(MonitoredService)
            if synthetic is not None:
                query = query.where(MonitoredService.synthetic == synthetic)
            query = query.order_by(MonitoredService.created_at.desc(), MonitoredService.id.desc())
            return [service_dict(row) for row in session.scalars(query.limit(limit).offset(offset))]

    def checks(self, *, limit=25, offset=0, service_id=None, status=None, synthetic=None):
        page_bounds(limit, offset)
        with self.transaction() as session:
            query = select(StoredCheck, MonitoredService).join(MonitoredService)
            if service_id is not None:
                query = query.where(StoredCheck.service_id == valid_id(service_id))
            if status is not None:
                from app.tools.models import CheckStatus

                if status not in set(CheckStatus):
                    raise StorageError("invalid_status")
                query = query.where(StoredCheck.status == status)
            if synthetic is not None:
                query = query.where(MonitoredService.synthetic == synthetic)
            query = query.order_by(StoredCheck.created_at.desc(), StoredCheck.id.desc())
            return [
                check_dict(row, service)
                for row, service in session.execute(query.limit(limit).offset(offset))
            ]

    def check(self, check_id):
        with self.transaction() as session:
            pair = session.execute(
                select(StoredCheck, MonitoredService)
                .join(MonitoredService)
                .where(StoredCheck.id == valid_id(check_id))
            ).first()
            return check_dict(*pair) if pair else None

    def incidents(self, *, limit=25, offset=0, service_id=None):
        page_bounds(limit, offset)
        with self.transaction() as session:
            query = select(Incident, MonitoredService).join(
                MonitoredService, Incident.service_id == MonitoredService.id
            )
            if service_id is not None:
                query = query.where(Incident.service_id == valid_id(service_id))
            query = query.order_by(Incident.created_at.desc(), Incident.id.desc())
            return [
                incident_dict(row, service)
                for row, service in session.execute(query.limit(limit).offset(offset))
            ]

    def create_open_incident(self, detected_check_id, *, severity="high"):
        """Storage foundation only; no HTTP or autonomous incident-creation workflow yet."""
        if severity not in {"warning", "high"}:
            raise StorageError("invalid_severity")
        with self.transaction() as session:
            check = session.get(StoredCheck, valid_id(detected_check_id))
            if check is None or check.status != "UNHEALTHY":
                raise StorageError("incident_requires_unhealthy_evidence")
            existing = session.scalar(
                select(Incident).where(Incident.detected_check_id == check.id)
            )
            if existing is None:
                existing = Incident(
                    service_id=check.service_id, detected_check_id=check.id, severity=severity
                )
                session.add(existing)
                session.flush()
            service = session.get(MonitoredService, check.service_id)
            return incident_dict(existing, service)
