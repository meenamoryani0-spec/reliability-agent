import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.actions.adapter import Receipt
from app.actions.models import RetryAction
from app.config import Settings
from app.db.migrate import HEAD, current_revision, downgrade, migration_transaction, upgrade
from app.db.models import Incident, StoredCheck, now
from app.db.repository import StorageError
from app.db.snapshots import snapshot_for
from app.main import create_app
from app.recovery.contracts import FlowPolicy
from app.recovery.evidence import evaluate
from app.recovery.models import RecoveryVerification
from app.recovery.reader import read_execution
from app.recovery.repository import RecoveryRepository
from app.recovery.service import RecoveryService
from app.tools.n8n_fixtures import PRIVATE_CANARY, execution_record
from app.tools.n8n_models import N8nReadResult
from app.tools.n8n_normalize import execution_evidence

FLOW = {
    "required_node_ids": ["trigger", "crm", "confirmation"],
    "completion_node_id": "confirmation",
}
SOURCE = "n8n-fixture-v1"
BINDING = {
    "source_hash": hashlib.sha256(SOURCE.encode()).hexdigest(),
    "mode": "fixture",
    "flows": {"wf-booking": FlowPolicy(**FLOW)},
}


def settings(database_config, **overrides):
    return Settings(
        _env_file=None,
        **{
            **database_config.model_dump(),
            "environment": "test",
            "n8n_mode": "fixture",
            "n8n_recovery_mode": "fixture",
            "n8n_recovery_flows": {"wf-booking": FLOW},
            **overrides,
        },
    )


def read_result(raw):
    return N8nReadResult(
        operation="execution", status="OK", synthetic=True, execution=execution_evidence(raw)
    )


def fresh_raw(action):
    raw = execution_record("2001", failed=False)
    raw.update(
        mode="retry",
        retryOf="1001",
        startedAt=action["dispatch_started_at"].isoformat(),
        stoppedAt=now().isoformat(),
    )
    return raw


@pytest.fixture
def recovery(engine):
    return RecoveryRepository(engine)


@pytest.fixture
def accepted(recovery):
    check_id = recovery.record(
        snapshot_for(read_result(execution_record("1001", failed=True)), SOURCE)
    )
    incident = recovery.ensure_incident(check_id)[0]
    binding = {"source_hash": BINDING["source_hash"], "mode": "fixture", "allowed": ["wf-booking"]}
    action = recovery.propose(incident["id"], check_id, **binding)
    recovery.claim(action["id"], **binding)
    recovery.mark_dispatch(action["id"])
    return recovery.finish(
        action["id"],
        dispatched=True,
        receipt=Receipt(
            id="2001", workflowId="wf-booking", mode="retry", retryOf="1001", status="running"
        ),
    )


def verify(recovery, action, raw=None):
    context = recovery.prepare(action["id"], **BINDING)
    result = read_result(raw or fresh_raw(action))
    check_id = recovery.record(snapshot_for(result, SOURCE))
    return recovery.finish_verification(
        action["id"], check_id, context["policy"], result.checked_at, **BINDING
    )[0]


def test_resolves_only_with_durable_scoped_proof_and_survives_restart(recovery, accepted, engine):
    assert recovery.incident(accepted["incident_id"])["status"] == "OPEN"
    proof = verify(recovery, accepted)
    assert proof["result"] == "VERIFIED" and proof["scope"] == "n8n_required_nodes"
    assert not proof["business_outcome_verified"] and not proof["root_cause_verified"]
    restarted = RecoveryRepository(engine)
    incident = restarted.incident(accepted["incident_id"])
    assert (
        incident["status"] == "RESOLVED" and incident["resolution_verification_id"] == proof["id"]
    )
    assert restarted.action(accepted["id"])["recovery_verified"]
    assert restarted.prepare(accepted["id"], **BINDING)["proof"] == proof
    assert PRIVATE_CANARY not in str(restarted.check(proof["check_id"]))


@pytest.mark.parametrize(
    "state", ["running", "waiting", "new", "unknown", "error", "crashed", "canceled"]
)
def test_unfinished_or_failed_never_resolves(recovery, accepted, state):
    raw = fresh_raw(accepted)
    raw["status"] = state
    proof = verify(recovery, accepted, raw)
    assert proof["result"] == (
        "NOT_RECOVERED" if state in {"error", "crashed", "canceled"} else "INCONCLUSIVE"
    )
    assert recovery.incident(accepted["incident_id"])["status"] == "OPEN"
    assert not recovery.action(accepted["id"])["recovery_verified"]


@pytest.mark.parametrize(
    "change,reason",
    [
        ("wrong_id", "identity_mismatch"),
        ("wrong_workflow", "identity_mismatch"),
        ("wrong_lineage", "identity_mismatch"),
        ("wrong_mode", "identity_mismatch"),
        ("no_data", "missing_execution_data"),
        ("missing_node", "missing_required_nodes"),
        ("unknown_node_status", "node_not_successful"),
        ("running_node", "node_not_successful"),
        ("wrong_last", "completion_node_not_observed"),
        ("missing_time", "invalid_timestamps"),
        ("old_start", "invalid_timestamps"),
        ("future_stop", "invalid_timestamps"),
        ("redacted", "missing_execution_data"),
        ("oversized", "missing_execution_data"),
    ],
)
def test_top_level_success_does_not_override_missing_proof(recovery, accepted, change, reason):
    raw = fresh_raw(accepted)
    if change == "wrong_id":
        raw["id"] = "9999"
    if change == "wrong_workflow":
        raw["workflowId"] = "other"
    if change == "wrong_lineage":
        raw["retryOf"] = "9999"
    if change == "wrong_mode":
        raw["mode"] = "manual"
    if change == "no_data":
        raw.pop("data")
    if change == "missing_node":
        raw["data"]["resultData"]["runData"].pop("Send confirmation")
    if change == "unknown_node_status":
        raw["data"]["resultData"]["runData"]["CRM"][0].pop("executionStatus")
    if change == "running_node":
        raw["data"]["resultData"]["runData"]["CRM"][0]["executionStatus"] = "running"
    if change == "wrong_last":
        raw["data"]["resultData"]["lastNodeExecuted"] = "CRM"
    if change == "missing_time":
        raw["stoppedAt"] = None
    if change == "old_start":
        raw["startedAt"] = (accepted["dispatch_started_at"] - timedelta(minutes=5)).isoformat()
    if change == "future_stop":
        raw["stoppedAt"] = (now() + timedelta(minutes=5)).isoformat()
    if change == "redacted":
        raw["data"]["redactionInfo"] = {"isRedacted": True}
    if change == "oversized":
        raw["dataTooLargeToDisplay"] = True
    proof = verify(recovery, accepted, raw)
    assert proof["result"] == "INCONCLUSIVE" and proof["reason"] == reason
    assert recovery.incident(accepted["incident_id"])["status"] == "OPEN"


def test_additional_failure_is_not_closed_by_one_successful_retry(recovery, accepted):
    extra = recovery.record(
        snapshot_for(read_result(execution_record("1003", failed=True)), SOURCE)
    )
    assert recovery.ensure_incident(extra)[0]["id"] == accepted["incident_id"]
    proof = verify(recovery, accepted)
    assert proof["reason"] == "additional_failure" and proof["result"] == "INCONCLUSIVE"
    assert recovery.incident(accepted["incident_id"])["status"] == "OPEN"


def test_original_failed_execution_repoll_does_not_reopen_but_new_failure_does(recovery, accepted):
    verify(recovery, accepted)
    check = recovery.record(
        snapshot_for(read_result(execution_record("1001", failed=True)), SOURCE)
    )
    old, created = recovery.ensure_incident(check)
    assert not created and old["status"] == "RESOLVED" and old["id"] == accepted["incident_id"]
    check = recovery.record(
        snapshot_for(read_result(execution_record("1003", failed=True)), SOURCE)
    )
    new, created = recovery.ensure_incident(check)
    assert created and new["status"] == "OPEN" and new["id"] != old["id"]


def test_failed_retry_observation_can_be_superseded_by_fresh_success(recovery, accepted):
    check = recovery.record(
        snapshot_for(read_result(execution_record("2001", failed=True)), SOURCE)
    )
    recovery.ensure_incident(check)
    assert verify(recovery, accepted)["result"] == "VERIFIED"


def test_concurrent_verification_has_one_durable_proof(recovery, accepted, engine):
    context = recovery.prepare(accepted["id"], **BINDING)
    result = read_result(fresh_raw(accepted))
    check = recovery.record(snapshot_for(result, SOURCE))

    def close(_):
        return RecoveryRepository(engine).finish_verification(
            accepted["id"], check, context["policy"], result.checked_at, **BINDING
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(close, range(4)))
    assert len({proof["id"] for proof, _ in results}) == 1
    assert sum(not reused for _, reused in results) == 1
    assert len(recovery.verifications()) == 1


def test_database_rejects_resolution_without_proof_and_forged_healthy_reference(
    recovery, accepted, engine
):
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            update(Incident)
            .where(Incident.id == accepted["incident_id"])
            .values(
                status="RESOLVED",
                resolved_at=now(),
                resolution_scope="n8n_required_nodes",
                resolution_verification_id=str(uuid4()),
                resolution_result="VERIFIED",
            )
        )
    with pytest.raises(IntegrityError), recovery.sessions.begin() as session:
        session.add(
            RecoveryVerification(
                action_id=accepted["id"],
                incident_id=accepted["incident_id"],
                service_id=accepted["service_id"],
                check_id=accepted["check_id"],
                check_status="HEALTHY",
                result="VERIFIED",
                reason="required_path_succeeded",
                original_execution_id="1001",
                new_execution_id="2001",
                workflow_id="wf-booking",
                policy=FLOW,
                observed_at=now(),
            )
        )
    assert recovery.incident(accepted["incident_id"])["status"] == "OPEN"


def test_proof_and_check_cannot_be_deleted_and_downgrade_preserves_audit(
    recovery, accepted, engine
):
    proof = verify(recovery, accepted)
    for table, identifier in [
        (RecoveryVerification, proof["id"]),
        (StoredCheck, proof["check_id"]),
    ]:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(delete(table).where(table.id == identifier))
    with pytest.raises(RuntimeError, match="history prevents downgrade"):
        downgrade(engine, "0004_approved_n8n_retry")
    assert current_revision(engine) == HEAD
    assert recovery.verification(proof["id"]) == proof


def test_migration_preserves_existing_actions_observations_and_constraints(
    recovery, accepted, engine
):
    # No proof exists, so a round trip through Phase 11 is safe.
    prior = recovery.action(accepted["id"])
    downgrade(engine, "0004_approved_n8n_retry")
    upgrade(engine)
    assert recovery.action(accepted["id"]) == prior
    assert recovery.incident(prior["incident_id"])["observation_count"] == 1
    assert verify(recovery, accepted)["result"] == "VERIFIED"


def test_read_unavailable_is_audited_without_resolving(recovery, accepted, database_config):
    async def scenario():
        reader = AsyncMock(side_effect=RuntimeError(PRIVATE_CANARY))
        service = RecoveryService(settings(database_config), reader=reader)
        try:
            result = await service.verify(accepted["id"])
            assert result["status"] == "INCONCLUSIVE" and result["durable_outcome"]
            assert result["verification"]["reason"] == "read_unavailable"
            assert PRIVATE_CANARY not in str(result)
        finally:
            await service.close()

    asyncio.run(scenario())
    assert recovery.incident(accepted["incident_id"])["status"] == "OPEN"


@pytest.mark.parametrize("failure", ["record", "finish"])
def test_storage_failure_cannot_close_incident(recovery, accepted, database_config, failure):
    async def scenario():
        service = RecoveryService(settings(database_config))
        if failure == "record":
            service.repository.record = Mock(side_effect=StorageError("storage_unavailable"))
        else:
            service.repository.finish_verification = Mock(
                side_effect=StorageError("storage_unavailable")
            )
        try:
            if failure == "record":
                with pytest.raises(StorageError):
                    await service.verify(accepted["id"])
            else:
                result = await service.verify(accepted["id"])
                assert not result["durable_outcome"] and result["check_id"]
        finally:
            await service.close()

    asyncio.run(scenario())
    assert recovery.incident(accepted["incident_id"])["status"] == "OPEN"
    assert recovery.verifications() == []


def test_service_reads_exact_retry_once_then_reuses_historical_proof(
    recovery, accepted, database_config
):
    async def scenario():
        reader = AsyncMock(wraps=read_execution)
        service = RecoveryService(settings(database_config), reader=reader)
        try:
            first = await service.verify(accepted["id"])
            second = await service.verify(accepted["id"])
            assert first["status"] == "VERIFIED" and not first["historical_proof_reused"]
            assert second["historical_proof_reused"] and reader.await_count == 1
            assert reader.call_args.args[1]["new_execution_id"] == "2001"
        finally:
            await service.close()

    asyncio.run(scenario())


def test_cancellation_drains_work_and_keeps_slot_until_complete(
    recovery, accepted, database_config
):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def reader(config, action):
            entered.set()
            await release.wait()
            return await read_execution(config, action)

        service = RecoveryService(settings(database_config), reader=reader)
        task = asyncio.create_task(service.verify(accepted["id"]))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(StorageError, match="recovery_busy"):
            await service.verify(accepted["id"])
        closer = asyncio.create_task(service.close())
        await asyncio.sleep(0)
        assert not closer.done()
        release.set()
        await closer
        assert recovery.incident(accepted["incident_id"])["status"] == "RESOLVED"

    asyncio.run(scenario())


@pytest.mark.parametrize("mismatch", ["source", "mode", "workflow", "pending"])
def test_binding_and_accepted_receipt_required(recovery, accepted, engine, mismatch):
    binding = dict(BINDING)
    if mismatch == "source":
        binding["source_hash"] = "0" * 64
    if mismatch == "mode":
        binding["mode"] = "live"
    if mismatch == "workflow":
        binding["flows"] = {}
    if mismatch == "pending":
        with engine.begin() as connection:
            connection.execute(
                update(RetryAction)
                .where(RetryAction.id == accepted["id"])
                .values(
                    state="UNKNOWN",
                    new_execution_id=None,
                    provider_state=None,
                    reason="provider_outcome_unknown",
                )
            )
    with pytest.raises(StorageError):
        recovery.prepare(accepted["id"], **binding)


def test_history_read_routes_and_no_http_verification(recovery, accepted, database_config):
    proof = verify(recovery, accepted)
    with TestClient(create_app(settings(database_config))) as client:
        assert client.get("/recovery").json()["scope"] == "n8n_required_nodes"
        assert client.get("/history/verifications").json()[0]["id"] == proof["id"]
        assert client.get("/history/verifications/" + proof["id"]).json()["result"] == "VERIFIED"
        assert client.get("/history/actions/" + accepted["id"]).json()["recovery_verified"]
        assert client.post("/recovery", json={"action_id": accepted["id"]}).status_code == 405
        assert client.post("/history/verifications").status_code == 405
        assert client.get("/history/verifications?limit=101").status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"environment": "production"},
        {"storage_mode": "disabled"},
        {"n8n_mode": "disabled"},
        {"n8n_recovery_flows": {}},
        {"n8n_recovery_mode": "live", "n8n_mode": "live"},
        {"n8n_recovery_flows": {"bad.id": FLOW}},
        {"n8n_recovery_flows": {"wf-booking": {**FLOW, "completion_node_id": "missing"}}},
        {"n8n_recovery_flows": {"wf-booking": {**FLOW, "required_node_ids": ["crm", "crm"]}}},
    ],
)
def test_invalid_recovery_configuration_is_rejected(database_config, overrides):
    with pytest.raises(ValidationError):
        settings(database_config, **overrides)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("observation", "observation_stale"),
        ("completion", "completion_stale"),
        ("policy", "original_failure_not_covered"),
        ("duplicate", "missing_required_nodes"),
        ("no_success_count", "node_not_successful"),
    ],
)
def test_pure_evidence_conservative_edge_cases(case, reason):
    at = now()
    action = {
        "new_execution_id": "2001",
        "execution_id": "1001",
        "workflow_id": "wf-booking",
        "dispatch_started_at": at - timedelta(minutes=10),
    }
    execution = execution_evidence(fresh_raw(action))
    original = execution_evidence(execution_record("1001", failed=True))
    policy, observed_at = FlowPolicy(**FLOW), at
    if case == "observation":
        observed_at = at - timedelta(minutes=3)
    if case == "completion":
        execution.stopped_at = at - timedelta(minutes=6)
    if case == "policy":
        policy = FlowPolicy(
            required_node_ids=["trigger", "confirmation"], completion_node_id="confirmation"
        )
    if case == "duplicate":
        execution.observed_nodes.append(execution.observed_nodes[0])
    if case == "no_success_count":
        execution.observed_nodes[1].successful_attempts = 0
    decision = evaluate(action, original, execution, policy, observed_at, at)
    assert decision.result == "INCONCLUSIVE" and decision.reason == reason


def test_sqlite_migration_failure_rolls_back_and_restores_enforcement(engine):
    if engine.dialect.name != "sqlite":
        # The PostgreSQL variant verifies transactional migration rollback too.
        with pytest.raises(RuntimeError), migration_transaction(engine) as connection:
            connection.exec_driver_sql("CREATE TABLE reliability.rollback_probe(id INTEGER)")
            raise RuntimeError("abort")
        from sqlalchemy import inspect

        assert not inspect(engine).has_table("rollback_probe", schema="reliability")
        return
    with pytest.raises(RuntimeError), migration_transaction(engine) as connection:
        connection.exec_driver_sql("CREATE TABLE rollback_probe(id INTEGER)")
        connection.exec_driver_sql(
            "INSERT INTO checks(id,service_id,kind,status,observed_at,created_at,payload) "
            "VALUES ('bad','missing','execution','HEALTHY','2026-10-17','2026-10-17','{}')"
        )
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert connection.scalar(select(func.count()).select_from(StoredCheck)) == 0


def test_changed_policy_cannot_authorize_an_observation_read_under_old_policy(recovery, accepted):
    context = recovery.prepare(accepted["id"], **BINDING)
    result = read_result(fresh_raw(accepted))
    check = recovery.record(snapshot_for(result, SOURCE))
    changed = {
        **BINDING,
        "flows": {
            "wf-booking": FlowPolicy(
                required_node_ids=["crm", "confirmation"], completion_node_id="confirmation"
            )
        },
    }
    proof, _ = recovery.finish_verification(
        accepted["id"], check, context["policy"], result.checked_at, **changed
    )
    assert proof["result"] == "INCONCLUSIVE" and proof["reason"] == "policy_changed"
    assert recovery.incident(accepted["incident_id"])["status"] == "OPEN"


def test_structured_provider_read_failure_is_saved_without_false_identity_diagnosis(
    recovery, accepted, database_config
):
    async def scenario():
        reader = AsyncMock(
            return_value=N8nReadResult(
                operation="execution",
                status="CHECK_FAILED",
                synthetic=True,
                reason="transport_error",
            )
        )
        service = RecoveryService(settings(database_config), reader=reader)
        try:
            result = await service.verify(accepted["id"])
            assert result["status"] == "INCONCLUSIVE"
            assert result["verification"]["reason"] == "read_unavailable"
            assert any(row["status"] == "CHECK_FAILED" for row in recovery.checks())
        finally:
            await service.close()

    asyncio.run(scenario())
    assert recovery.incident(accepted["incident_id"])["status"] == "OPEN"


def test_new_failure_racing_resolution_always_remains_unresolved(recovery, accepted, engine):
    from threading import Barrier

    context = recovery.prepare(accepted["id"], **BINDING)
    result = read_result(fresh_raw(accepted))
    healthy = recovery.record(snapshot_for(result, SOURCE))
    failed = recovery.record(
        snapshot_for(read_result(execution_record("1003", failed=True)), SOURCE)
    )
    barrier = Barrier(2)

    def resolve():
        barrier.wait(timeout=10)
        return RecoveryRepository(engine).finish_verification(
            accepted["id"], healthy, context["policy"], result.checked_at, **BINDING
        )

    def detect():
        barrier.wait(timeout=10)
        return RecoveryRepository(engine).ensure_incident(failed)

    with ThreadPoolExecutor(max_workers=2) as pool:
        proof_task, incident_task = pool.submit(resolve), pool.submit(detect)
        proof, _ = proof_task.result()
        linked, _ = incident_task.result()
    assert recovery.incident(linked["id"])["status"] == "OPEN"
    assert proof["result"] in {"VERIFIED", "INCONCLUSIVE"}
    if proof["result"] == "VERIFIED":
        assert linked["id"] != accepted["incident_id"]


def test_recovery_is_disabled_by_default_and_production_history_is_hidden():
    config = Settings(_env_file=None, environment="production")
    assert config.n8n_recovery_mode == "disabled" and config.n8n_recovery_flows == {}
    with TestClient(create_app(config)) as client:
        for path in ("/recovery", "/history/verifications", f"/history/verifications/{uuid4()}"):
            assert client.get(path).status_code == 404

    async def scenario():
        service = RecoveryService(config)
        try:
            with pytest.raises(StorageError, match="recovery_disabled"):
                await service.verify(str(uuid4()))
        finally:
            await service.close()

    asyncio.run(scenario())
