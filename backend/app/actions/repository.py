"""Transactional proposals and compare-and-set approval/dispatch transitions."""

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.actions.models import RetryAction
from app.db.models import Incident, IncidentObservation, MonitoredService, StoredCheck, now
from app.db.repository import HistoryRepository, StorageError, page_bounds, valid_id
from app.db.snapshots import Snapshot
from app.recovery.models import RecoveryVerification
from app.tools.n8n_models import ExecutionId, ResourceId
from app.tools.n8n_normalize import ProviderMetadata

APPROVAL_WINDOW_SECONDS = 300


class StoredExecution(ProviderMetadata):
    id: ExecutionId
    workflow_id: ResourceId
    execution_state: str
    data_availability: str


def action_dict(row, link, service, proof=None):
    return {
        "id": row.id,
        "action": "retry_n8n_execution",
        "check_id": row.check_id,
        "incident_id": link.incident_id,
        "service_id": link.service_id,
        "execution_id": row.execution_id,
        "workflow_id": row.workflow_id,
        "target_fingerprint": row.source_hash,
        "mode": row.mode,
        "synthetic": service.synthetic,
        "state": row.state,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "approved_at": row.approved_at,
        "dispatch_started_at": row.dispatch_started_at,
        "completed_at": row.completed_at,
        "new_execution_id": row.new_execution_id,
        "provider_state": row.provider_state,
        "reason": row.reason,
        "approval_method": "local_operator_duplicate_effects_ack" if row.approved_at else None,
        "load_workflow": False,
        "recovery_verified": proof is not None,
        "resolution_verification_id": proof.id if proof else None,
        "resolution_scope": "n8n_required_nodes" if proof else None,
        "business_outcome_verified": False,
        "risk": "Retry may repeat external side effects, including messages or payments.",
    }


class ActionRepository(HistoryRepository):
    @staticmethod
    def _query():
        return (
            select(RetryAction, IncidentObservation, MonitoredService, RecoveryVerification)
            .join(IncidentObservation, RetryAction.check_id == IncidentObservation.check_id)
            .join(MonitoredService, IncidentObservation.service_id == MonitoredService.id)
            .join(Incident, IncidentObservation.incident_id == Incident.id)
            .outerjoin(
                RecoveryVerification,
                (Incident.resolution_verification_id == RecoveryVerification.id)
                & (RecoveryVerification.action_id == RetryAction.id),
            )
        )

    def actions(self, *, limit=25, offset=0):
        page_bounds(limit, offset)
        with self.transaction() as session:
            return [
                action_dict(*row)
                for row in session.execute(
                    self._query()
                    .order_by(RetryAction.created_at.desc(), RetryAction.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ]

    def action(self, action_id):
        with self.transaction() as session:
            row = session.execute(
                self._query().where(RetryAction.id == valid_id(action_id))
            ).first()
            return action_dict(*row) if row else None

    @staticmethod
    def _bound_check(session, incident_id, check_id, source_hash, mode, allowed, at):
        link = session.get(IncidentObservation, valid_id(check_id))
        if link is None or link.incident_id != valid_id(incident_id):
            raise StorageError("retry_requires_incident_evidence")
        incident = session.get(Incident, link.incident_id)
        check = session.get(StoredCheck, link.check_id)
        service = session.get(MonitoredService, link.service_id)
        if (
            incident.status not in {"OPEN", "INVESTIGATING"}
            or service.category != "n8n"
            or check.kind != "execution"
            or check.status != "UNHEALTHY"
            or service.synthetic != (mode == "fixture")
            or mode not in {"fixture", "live"}
        ):
            raise StorageError("retry_not_eligible")
        try:
            evidence = StoredExecution.model_validate(check.payload.get("evidence"))
        except ValueError:
            raise StorageError("retry_not_eligible") from None
        if (
            evidence.execution_state != "error"
            or evidence.data_availability != "present"
            or evidence.workflow_id not in allowed
            or service.component != "workflow:" + evidence.workflow_id
        ):
            raise StorageError("retry_not_eligible")
        expected = Snapshot(
            category="n8n",
            component=service.component,
            source_hash=source_hash,
            synthetic=mode == "fixture",
            kind=check.kind,
            status=check.status,
            observed_at=check.observed_at,
            payload=check.payload,
        )
        if expected.service_id != service.id:
            raise StorageError("retry_target_changed")
        if check.created_at > at + timedelta(seconds=5) or at >= check.created_at + timedelta(
            seconds=APPROVAL_WINDOW_SECONDS
        ):
            raise StorageError("retry_evidence_stale")
        return evidence, check

    def propose(self, incident_id, check_id, *, source_hash, mode, allowed, at=None):
        at = at or now()
        with self.transaction(write=True) as session:
            evidence, check = self._bound_check(
                session, incident_id, check_id, source_hash, mode, allowed, at
            )
            insert = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
            identifier = session.execute(
                insert(RetryAction)
                .values(
                    check_id=check.id,
                    source_hash=source_hash,
                    execution_id=evidence.id,
                    workflow_id=evidence.workflow_id,
                    mode=mode,
                    state="PENDING",
                    created_at=at,
                    expires_at=min(
                        at + timedelta(seconds=APPROVAL_WINDOW_SECONDS),
                        check.created_at + timedelta(seconds=APPROVAL_WINDOW_SECONDS),
                    ),
                )
                .on_conflict_do_nothing()
                .returning(RetryAction.id)
            ).scalar_one_or_none()
            if identifier is None:
                identifier = session.scalar(
                    select(RetryAction.id).where(
                        RetryAction.source_hash == source_hash,
                        RetryAction.execution_id == evidence.id,
                    )
                )
            row = session.execute(self._query().where(RetryAction.id == identifier)).one()
            return action_dict(*row)

    def claim(self, action_id, *, source_hash, mode, allowed, at=None):
        at = at or now()
        with self.transaction(write=True) as session:
            row = session.get(RetryAction, valid_id(action_id))
            if row is None:
                raise StorageError("action_not_found")
            if row.state != "PENDING":
                raise StorageError("action_already_consumed")
            if at >= row.expires_at or at < row.created_at:
                raise StorageError("approval_expired")
            link = session.get(IncidentObservation, row.check_id)
            evidence, _ = self._bound_check(
                session, link.incident_id, row.check_id, source_hash, mode, allowed, at
            )
            if (
                row.source_hash != source_hash
                or row.mode != mode
                or row.workflow_id != evidence.workflow_id
                or row.execution_id != evidence.id
            ):
                raise StorageError("retry_target_changed")
            changed = session.execute(
                update(RetryAction)
                .where(RetryAction.id == row.id, RetryAction.state == "PENDING")
                .values(state="EXECUTING", approved_at=at)
                .returning(RetryAction.id)
            ).scalar_one_or_none()
            if changed is None:
                raise StorageError("action_already_consumed")
            return action_dict(
                *session.execute(self._query().where(RetryAction.id == row.id)).one()
            )

    def mark_dispatch(self, action_id):
        with self.transaction(write=True) as session:
            changed = session.execute(
                update(RetryAction)
                .where(
                    RetryAction.id == valid_id(action_id),
                    RetryAction.state == "EXECUTING",
                    RetryAction.dispatch_started_at.is_(None),
                    RetryAction.expires_at > now(),
                )
                .values(dispatch_started_at=now())
                .returning(RetryAction.id)
            ).scalar_one_or_none()
            if changed is None:
                raise StorageError("action_not_dispatchable")

    def finish(self, action_id, *, receipt=None, dispatched=False):
        from app.actions.adapter import Receipt

        with self.transaction(write=True) as session:
            row = session.get(RetryAction, valid_id(action_id))
            if (
                row is None
                or row.state != "EXECUTING"
                or (row.dispatch_started_at is not None) != dispatched
            ):
                raise StorageError("action_not_executing")
            if receipt is not None:
                value = Receipt.model_validate(receipt.model_dump())
                if (
                    value.id == row.execution_id
                    or value.retryOf != row.execution_id
                    or value.workflowId != row.workflow_id
                ):
                    raise StorageError("retry_identity_mismatch")
                if not dispatched:
                    raise StorageError("action_not_dispatchable")
                values = {
                    "state": "ACCEPTED",
                    "new_execution_id": value.id,
                    "provider_state": value.status,
                }
            else:
                values = {
                    "state": "UNKNOWN" if dispatched else "REJECTED",
                    "reason": "provider_outcome_unknown" if dispatched else "preflight_failed",
                }
            changed = session.execute(
                update(RetryAction)
                .where(RetryAction.id == row.id, RetryAction.state == "EXECUTING")
                .values(**values, completed_at=now())
                .returning(RetryAction.id)
            ).scalar_one_or_none()
            if changed is None:
                raise StorageError("action_not_executing")
            return action_dict(
                *session.execute(self._query().where(RetryAction.id == row.id)).one()
            )
