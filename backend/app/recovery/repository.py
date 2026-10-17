"""Re-evaluate persisted observations and close only with a same-transaction proof."""

from sqlalchemy import or_, select

from app.actions.repository import ActionRepository
from app.db.models import Incident, IncidentObservation, StoredCheck, now
from app.db.repository import StorageError, page_bounds, valid_id
from app.db.snapshots import Snapshot
from app.recovery.contracts import Decision, FlowPolicy
from app.recovery.evidence import evaluate
from app.recovery.models import RecoveryVerification
from app.tools.n8n_models import ExecutionEvidence


def stored_execution(check):
    return ExecutionEvidence.model_validate(
        {"summary": "Stored observation", **check.payload["evidence"]}
    )


def verification_dict(row):
    return {
        "id": row.id,
        "action_id": row.action_id,
        "incident_id": row.incident_id,
        "service_id": row.service_id,
        "check_id": row.check_id,
        "result": row.result,
        "reason": row.reason,
        "original_execution_id": row.original_execution_id,
        "new_execution_id": row.new_execution_id,
        "workflow_id": row.workflow_id,
        "policy": row.policy,
        "observed_at": row.observed_at,
        "created_at": row.created_at,
        "scope": "n8n_required_nodes",
        "recovery_verified": row.result == "VERIFIED",
        "business_outcome_verified": False,
        "root_cause_verified": False,
    }


class RecoveryRepository(ActionRepository):
    def _context(self, session, action_id, *, source_hash, mode, flows, lock=False):
        pair = session.execute(
            self._query().where(self._query_action_id() == valid_id(action_id))
        ).first()
        if pair is None:
            raise StorageError("action_not_found")
        row, link, service, *_ = pair
        if lock:
            self.lock_service(session, service.id)
        incident = session.get(Incident, link.incident_id)
        if (
            row.state != "ACCEPTED"
            or row.source_hash != source_hash
            or row.mode != mode
            or service.synthetic != (mode == "fixture")
            or mode not in {"fixture", "live"}
            or service.category != "n8n"
            or link.kind != "execution"
        ):
            raise StorageError("recovery_not_eligible")
        original = session.get(StoredCheck, row.check_id)
        expected = Snapshot(
            category="n8n",
            component="workflow:" + row.workflow_id,
            source_hash=source_hash,
            synthetic=mode == "fixture",
            kind="execution",
            status=original.status,
            observed_at=original.observed_at,
            payload=original.payload,
        )
        if expected.service_id != service.id:
            raise StorageError("recovery_target_changed")
        proof = (
            session.get(RecoveryVerification, incident.resolution_verification_id)
            if (incident.resolution_verification_id)
            else None
        )
        if proof is not None and proof.action_id == row.id:
            return row, incident, original, None, proof
        if incident.status not in {"OPEN", "INVESTIGATING"}:
            raise StorageError("incident_already_resolved")
        if row.workflow_id not in flows:
            raise StorageError("recovery_flow_not_configured")
        policy = FlowPolicy.model_validate(flows[row.workflow_id].model_dump())
        return row, incident, original, policy, None

    @staticmethod
    def _query_action_id():
        from app.actions.models import RetryAction

        return RetryAction.id

    def prepare(self, action_id, **binding):
        with self.transaction() as session:
            row, incident, original, policy, proof = self._context(session, action_id, **binding)
            return {
                "action": self.action_values(row, incident),
                "original": stored_execution(original),
                "policy": policy,
                "proof": verification_dict(proof) if proof else None,
            }

    @staticmethod
    def action_values(row, incident):
        return {
            "id": row.id,
            "incident_id": incident.id,
            "service_id": incident.service_id,
            "execution_id": row.execution_id,
            "new_execution_id": row.new_execution_id,
            "workflow_id": row.workflow_id,
            "dispatch_started_at": row.dispatch_started_at,
        }

    def finish_verification(self, action_id, check_id, policy, observed_at, **binding):
        with self.transaction(write=True) as session:
            row, incident, original, current_policy, proof = self._context(
                session, action_id, lock=True, **binding
            )
            if proof:
                return verification_dict(proof), True
            decision = Decision(result="INCONCLUSIVE", reason="read_unavailable")
            check = session.get(StoredCheck, valid_id(check_id)) if check_id else None
            if policy != current_policy:
                decision = Decision(result="INCONCLUSIVE", reason="policy_changed")
            elif check is not None:
                if check.status == "CHECK_FAILED":
                    decision = Decision(result="INCONCLUSIVE", reason="read_unavailable")
                elif check.service_id != incident.service_id or check.kind != "execution":
                    decision = Decision(result="INCONCLUSIVE", reason="identity_mismatch")
                else:
                    try:
                        decision = evaluate(
                            self.action_values(row, incident),
                            stored_execution(original),
                            stored_execution(check),
                            current_policy,
                            check.observed_at,
                            now(),
                        )
                    except (ValueError, KeyError, TypeError):
                        decision = Decision(result="INCONCLUSIVE", reason="missing_execution_data")
            if decision.result == "VERIFIED":
                # A shared incident can contain unrelated executions. One retry cannot
                # recover those, or a later failure of its own new execution.
                evidence = StoredCheck.payload["evidence"]
                identifier = evidence["id"].as_string()
                workflow = evidence["workflow_id"].as_string()
                extra = session.scalar(
                    select(StoredCheck.id)
                    .join(IncidentObservation, StoredCheck.id == IncidentObservation.check_id)
                    .where(
                        IncidentObservation.incident_id == incident.id,
                        or_(
                            identifier.is_(None),
                            workflow.is_(None),
                            identifier.not_in([row.execution_id, row.new_execution_id]),
                            workflow != row.workflow_id,
                            (identifier == row.new_execution_id)
                            & (StoredCheck.observed_at > check.observed_at),
                        ),
                    )
                    .limit(1)
                )
                if extra:
                    decision = Decision(result="INCONCLUSIVE", reason="additional_failure")
            same_service = (
                check and check.service_id == incident.service_id and check.kind == "execution"
            )
            verification = RecoveryVerification(
                action_id=row.id,
                incident_id=incident.id,
                service_id=incident.service_id,
                check_id=check.id if same_service else None,
                check_status=check.status if same_service else None,
                result=decision.result,
                reason=decision.reason,
                original_execution_id=row.execution_id,
                new_execution_id=row.new_execution_id,
                workflow_id=row.workflow_id,
                policy=current_policy.model_dump(mode="json"),
                observed_at=check.observed_at if check else observed_at,
            )
            session.add(verification)
            session.flush()
            if decision.result == "VERIFIED":
                incident.status = "RESOLVED"
                incident.resolution_verification_id = verification.id
                incident.resolution_result = "VERIFIED"
                incident.resolution_scope = "n8n_required_nodes"
                incident.resolved_at = now()
                session.flush()
            return verification_dict(verification), False

    def verifications(self, *, limit=25, offset=0):
        page_bounds(limit, offset)
        with self.transaction() as session:
            return [
                verification_dict(row)
                for row in session.scalars(
                    select(RecoveryVerification)
                    .order_by(
                        RecoveryVerification.created_at.desc(), RecoveryVerification.id.desc()
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ]

    def verification(self, verification_id):
        with self.transaction() as session:
            row = session.get(RecoveryVerification, valid_id(verification_id))
            return verification_dict(row) if row else None
