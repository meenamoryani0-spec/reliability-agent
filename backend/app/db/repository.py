"""One transaction/session per operation; no arbitrary query or delete API."""

from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    ACTIVE_INCIDENT,
    Incident,
    IncidentAssessment,
    IncidentObservation,
    MonitoredService,
    StoredCheck,
    now,
)
from app.db.snapshots import Snapshot
from app.recovery.models import RecoveryVerification


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


def incident_dict(row, service, count=0, first=None, last=None):
    return {
        "id": row.id,
        "service_id": row.service_id,
        "detected_check_id": row.detected_check_id,
        "category": service.category,
        "component": service.component,
        "kind": row.kind,
        "title": f"Unhealthy {service.category} {row.kind} observation",
        "status": row.status,
        "severity": row.severity,
        "created_at": row.created_at,
        "synthetic": service.synthetic,
        "observation_count": count or 0,
        "first_observed_at": first,
        "last_observed_at": last,
        "root_cause_verified": False,
        "root_cause": None,
        "verified": row.status == "RESOLVED",
        "recovery_verified": row.status == "RESOLVED",
        "business_outcome_verified": False,
        "resolution_verification_id": row.resolution_verification_id,
        "resolution_scope": row.resolution_scope,
        "resolved_at": row.resolved_at,
    }


class HistoryRepository:
    def __init__(self, engine):
        self.engine = engine
        self.sessions = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def transaction(self, *, write=False):
        try:
            with self.sessions.begin() as session:
                if write and self.engine.dialect.name == "sqlite":
                    session.connection(execution_options={"sqlite_write": True})
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

    @staticmethod
    def _incident_query():
        stats = (
            select(
                IncidentObservation.incident_id,
                func.count().label("observation_count"),
                func.min(StoredCheck.observed_at).label("first_observed_at"),
                func.max(StoredCheck.observed_at).label("last_observed_at"),
            )
            .join(StoredCheck, StoredCheck.id == IncidentObservation.check_id)
            .group_by(IncidentObservation.incident_id)
            .subquery()
        )
        return (
            select(
                Incident,
                MonitoredService,
                stats.c.observation_count,
                stats.c.first_observed_at,
                stats.c.last_observed_at,
            )
            .join(MonitoredService, Incident.service_id == MonitoredService.id)
            .outerjoin(stats, stats.c.incident_id == Incident.id)
        )

    def incidents(self, *, limit=25, offset=0, service_id=None, synthetic=None):
        page_bounds(limit, offset)
        with self.transaction() as session:
            query = self._incident_query()
            if service_id is not None:
                query = query.where(Incident.service_id == valid_id(service_id))
            if synthetic is not None:
                query = query.where(MonitoredService.synthetic == synthetic)
            query = query.order_by(Incident.created_at.desc(), Incident.id.desc())
            return [
                incident_dict(*row) for row in session.execute(query.limit(limit).offset(offset))
            ]

    def incident(self, incident_id):
        with self.transaction() as session:
            row = session.execute(
                self._incident_query().where(Incident.id == valid_id(incident_id))
            ).first()
            return incident_dict(*row) if row else None

    def incident_observations(self, incident_id, *, limit=25, offset=0):
        page_bounds(limit, offset)
        identifier = valid_id(incident_id)
        with self.transaction() as session:
            query = (
                select(StoredCheck, MonitoredService)
                .join(IncidentObservation, IncidentObservation.check_id == StoredCheck.id)
                .join(MonitoredService, MonitoredService.id == StoredCheck.service_id)
                .where(IncidentObservation.incident_id == identifier)
                .order_by(
                    StoredCheck.observed_at.desc(),
                    StoredCheck.created_at.desc(),
                    StoredCheck.id.desc(),
                )
            )
            return [check_dict(*row) for row in session.execute(query.limit(limit).offset(offset))]

    def create_open_incident(self, detected_check_id, *, severity="high"):
        return self.ensure_incident(detected_check_id, severity=severity)[0]

    def save_assessments(self, drafts):
        from app.agent.conclusions import supports
        from app.agent.tool_models import ToolResult
        from app.db.assessment import AssessmentDraft

        if not isinstance(drafts, list) or not 1 <= len(drafts) <= 8:
            raise StorageError("invalid_assessments")
        values = [AssessmentDraft.model_validate(value.model_dump()) for value in drafts]
        with self.transaction(write=True) as session:
            insert = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
            identifiers = []
            for value in values:
                linked = session.get(IncidentObservation, value.check_id)
                if linked is None:
                    raise StorageError("assessment_requires_incident_evidence")
                check = session.get(StoredCheck, value.check_id)
                service = session.get(MonitoredService, check.service_id)
                evidence = ToolResult(
                    name=None,
                    status="OK",
                    data={
                        "status": check.status,
                        "service": service.category,
                        "component": service.component,
                        "evidence": check.payload.get("evidence", {}),
                    },
                )
                if not supports(value.hypothesis, evidence):
                    raise StorageError("unsupported_assessment")
                if value.inference_source == "scripted_fixture" and not service.synthetic:
                    raise StorageError("assessment_provenance_mismatch")
                session.execute(
                    insert(IncidentAssessment)
                    .values(
                        check_id=value.check_id,
                        hypothesis=value.hypothesis,
                        recommended_steps=value.recommended_steps,
                        inference_source=value.inference_source,
                        root_cause=None,
                    )
                    .on_conflict_do_nothing(index_elements=["check_id"])
                )
                identifiers.append(value.check_id)
            return list(dict.fromkeys(identifiers))

    def incident_assessments(self, incident_id, *, limit=25, offset=0):
        page_bounds(limit, offset)
        with self.transaction() as session:
            query = (
                select(IncidentAssessment)
                .join(
                    IncidentObservation, IncidentObservation.check_id == IncidentAssessment.check_id
                )
                .where(IncidentObservation.incident_id == valid_id(incident_id))
                .order_by(IncidentAssessment.created_at.desc(), IncidentAssessment.check_id.desc())
            )
            return [
                {
                    "check_id": row.check_id,
                    "hypothesis": row.hypothesis,
                    "recommended_steps": row.recommended_steps,
                    "inference_source": row.inference_source,
                    "root_cause": row.root_cause,
                    "root_cause_verified": False,
                    "created_at": row.created_at,
                }
                for row in session.scalars(query.limit(limit).offset(offset))
            ]

    def ensure_incident(self, detected_check_id, *, severity="high"):
        """Atomically reuse one unresolved incident per service/kind and link each check once."""
        if not isinstance(severity, str) or severity not in {"warning", "high"}:
            raise StorageError("invalid_severity")
        with self.transaction(write=True) as session:
            check = session.get(StoredCheck, valid_id(detected_check_id))
            if check is None or check.status != "UNHEALTHY":
                raise StorageError("incident_requires_unhealthy_evidence")
            self.lock_service(session, check.service_id)
            linked = session.get(IncidentObservation, check.id)
            created = False
            if linked is not None:
                identifier = linked.incident_id
            else:
                insert = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
                historical = (
                    session.scalar(
                        select(Incident.id)
                        .join(
                            RecoveryVerification,
                            Incident.resolution_verification_id == RecoveryVerification.id,
                        )
                        .where(
                            Incident.service_id == check.service_id,
                            Incident.kind == check.kind,
                            Incident.status == "RESOLVED",
                            RecoveryVerification.original_execution_id
                            == check.payload.get("evidence", {}).get("id", ""),
                            RecoveryVerification.workflow_id
                            == check.payload.get("evidence", {}).get("workflow_id", ""),
                        )
                        .limit(1)
                    )
                    if check.kind == "execution"
                    else None
                )
                identifier = (
                    historical
                    or session.execute(
                        insert(Incident)
                        .values(
                            service_id=check.service_id,
                            detected_check_id=check.id,
                            kind=check.kind,
                            evidence_status="UNHEALTHY",
                            status="OPEN",
                            severity=severity,
                        )
                        # Same-check races can conflict with detected_check_id before
                        # the active-key index. Handle either uniqueness constraint.
                        .on_conflict_do_nothing()
                        .returning(Incident.id)
                    ).scalar_one_or_none()
                )
                created = identifier is not None and historical is None
                if identifier is None:
                    identifier = session.scalar(
                        select(Incident.id).where(
                            Incident.service_id == check.service_id,
                            Incident.kind == check.kind,
                            ACTIVE_INCIDENT,
                        )
                    )
                if identifier is None:
                    raise StorageError("incident_detection_unavailable")
                session.execute(
                    insert(IncidentObservation)
                    .values(
                        check_id=check.id,
                        incident_id=identifier,
                        service_id=check.service_id,
                        kind=check.kind,
                        check_status="UNHEALTHY",
                    )
                    .on_conflict_do_nothing(index_elements=["check_id"])
                )
            row = session.execute(self._incident_query().where(Incident.id == identifier)).one()
            return incident_dict(*row), created

    @staticmethod
    def lock_service(session, service_id):
        session.scalar(
            select(MonitoredService).where(MonitoredService.id == service_id).with_for_update()
        )

    def actions(self, *, limit=25, offset=0):
        from app.actions.repository import ActionRepository

        return ActionRepository(self.engine).actions(limit=limit, offset=offset)

    def action(self, action_id):
        from app.actions.repository import ActionRepository

        return ActionRepository(self.engine).action(action_id)

    def verifications(self, *, limit=25, offset=0):
        from app.recovery.repository import RecoveryRepository

        return RecoveryRepository(self.engine).verifications(limit=limit, offset=offset)

    def verification(self, verification_id):
        from app.recovery.repository import RecoveryRepository

        return RecoveryRepository(self.engine).verification(verification_id)
