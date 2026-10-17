import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, update

from app.actions.adapter import Receipt, retry_client
from app.actions.models import RetryAction
from app.actions.repository import ActionRepository
from app.actions.service import ActionService
from app.config import Settings
from app.db.migrate import HEAD, current_revision, downgrade, upgrade
from app.db.models import now
from app.db.repository import StorageError
from app.db.snapshots import snapshot_for, source_for
from app.main import create_app
from app.tools.n8n import N8nService
from app.tools.n8n_fixtures import fixture_client


def config(database_config, **options):
    return Settings(
        **{
            **database_config.model_dump(),
            "environment": "test",
            "n8n_mode": "fixture",
            "n8n_retry_mode": "fixture",
            "n8n_retry_workflow_ids": ["wf-booking"],
            **options,
        },
        _env_file=None,
    )


@pytest.fixture
def action_repository(engine):
    return ActionRepository(engine)


@pytest.fixture
def evidence(action_repository, database_config):
    settings = config(database_config)
    result = asyncio.run(
        N8nService("fixture", fixture_client()).read("execution", execution_id="1001")
    )
    check_id = action_repository.record(snapshot_for(result, source_for(result, settings)))
    incident_id = action_repository.ensure_incident(check_id)[0]["id"]
    return incident_id, check_id


POLICY = {
    "source_hash": hashlib.sha256(b"n8n-fixture-v1").hexdigest(),
    "mode": "fixture",
    "allowed": ["wf-booking"],
}


def propose(repository, evidence):
    return repository.propose(*evidence, **POLICY)


def accepted_receipt():
    return Receipt(
        id="2001", workflowId="wf-booking", mode="retry", retryOf="1001", status="running"
    )


def test_proposal_is_bound_and_persistent_replay_never_extends_approval(
    action_repository, evidence
):
    first = propose(action_repository, evidence)
    second = propose(action_repository, evidence)
    assert first == second and first["state"] == "PENDING" and first["approved_at"] is None
    assert first["check_id"] == evidence[1] and first["incident_id"] == evidence[0]
    assert first["synthetic"] and not first["load_workflow"] and not first["recovery_verified"]
    assert first["expires_at"] <= first["created_at"] + timedelta(seconds=300)


def test_parallel_proposal_and_claim_each_have_one_winner(action_repository, evidence):
    with ThreadPoolExecutor(max_workers=8) as pool:
        actions = list(pool.map(lambda _: propose(action_repository, evidence), range(16)))
    assert len({row["id"] for row in actions}) == 1
    barrier = Barrier(8)

    def claim(_):
        barrier.wait(timeout=10)
        try:
            action_repository.claim(actions[0]["id"], **POLICY)
            return "claimed"
        except StorageError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(8)))
    assert results.count("claimed") == 1 and results.count("action_already_consumed") == 7
    assert action_repository.action(actions[0]["id"])["state"] == "EXECUTING"


@pytest.mark.parametrize(
    "fault", ["wrong_incident", "wrong_source", "wrong_mode", "not_allowlisted", "stale"]
)
def test_proposal_rejects_invalid_scope_and_stale_evidence(action_repository, evidence, fault):
    policy = dict(POLICY)
    incident_id, check_id = evidence
    if fault == "wrong_incident":
        incident_id = str(uuid4())
    if fault == "wrong_source":
        policy["source_hash"] = "a" * 64
    if fault == "wrong_mode":
        policy["mode"] = "live"
    if fault == "not_allowlisted":
        policy["allowed"] = ["different"]
    if fault == "stale":
        policy["at"] = now() + timedelta(seconds=301)
    with pytest.raises(StorageError):
        action_repository.propose(incident_id, check_id, **policy)
    assert action_repository.actions() == []


@pytest.mark.parametrize("fault", ["expired", "changed_source", "removed_allowlist"])
def test_approval_rechecks_expiry_and_current_policy(action_repository, evidence, fault):
    action = propose(action_repository, evidence)
    policy = dict(POLICY)
    if fault == "expired":
        policy["at"] = action["expires_at"]
    if fault == "changed_source":
        policy["source_hash"] = "b" * 64
    if fault == "removed_allowlist":
        policy["allowed"] = []
    with pytest.raises(StorageError):
        action_repository.claim(action["id"], **policy)
    assert action_repository.action(action["id"])["state"] == "PENDING"


def test_dispatch_cannot_start_after_expiry_even_if_approval_was_claimed(
    action_repository, evidence
):
    action = propose(action_repository, evidence)
    action_repository.claim(action["id"], **POLICY)
    with action_repository.transaction() as session:
        session.execute(
            update(RetryAction)
            .where(RetryAction.id == action["id"])
            .values(
                created_at=now() - timedelta(seconds=400), expires_at=now() - timedelta(seconds=1)
            )
        )
    with pytest.raises(StorageError):
        action_repository.mark_dispatch(action["id"])
    assert action_repository.action(action["id"])["dispatch_started_at"] is None


def test_dispatch_and_terminal_receipt_are_one_shot_and_do_not_resolve(action_repository, evidence):
    action = propose(action_repository, evidence)
    action_repository.claim(action["id"], **POLICY)
    action_repository.mark_dispatch(action["id"])
    with pytest.raises(StorageError):
        action_repository.mark_dispatch(action["id"])
    finished = action_repository.finish(action["id"], dispatched=True, receipt=accepted_receipt())
    assert finished["state"] == "ACCEPTED" and finished["new_execution_id"] == "2001"
    assert (
        not finished["recovery_verified"]
        and action_repository.incident(evidence[0])["status"] == "OPEN"
    )
    with pytest.raises(StorageError):
        action_repository.finish(action["id"], dispatched=True)
    with pytest.raises(StorageError):
        action_repository.claim(action["id"], **POLICY)
    assert propose(action_repository, evidence)["id"] == action["id"]


@pytest.mark.parametrize(
    "fault", ["unapproved", "fabricated_receipt", "invalid_state", "invalid_check"]
)
def test_database_guards_reject_impossible_audit_records(action_repository, evidence, fault):
    action = propose(action_repository, evidence)
    values = {
        "unapproved": {"state": "EXECUTING"},
        "fabricated_receipt": {"new_execution_id": "2001"},
        "invalid_state": {"state": "RESOLVED"},
        "invalid_check": {"check_id": str(uuid4())},
    }[fault]
    with pytest.raises(StorageError):
        with action_repository.transaction() as session:
            session.execute(
                update(RetryAction).where(RetryAction.id == action["id"]).values(**values)
            )
    assert action_repository.action(action["id"])["state"] == "PENDING"


def test_migration_roundtrip_preserves_nonempty_prior_history_and_incident(
    engine, evidence, action_repository
):
    prior = action_repository.incident(evidence[0])
    downgrade(engine, "0003_incident_assessments")
    schema = "reliability" if engine.dialect.name == "postgresql" else None
    assert "retry_actions" not in inspect(engine).get_table_names(schema=schema)
    upgrade(engine)
    assert current_revision(engine) == HEAD and action_repository.incident(evidence[0]) == prior
    assert action_repository.actions() == []


@pytest.mark.parametrize(
    "fault", ["none", "preflight", "post_timeout", "mark_audit", "finish_audit"]
)
def test_action_execution_separates_preflight_post_and_audit_failures(
    engine, database_config, evidence, monkeypatch, fault
):
    client = Mock(
        preflight=AsyncMock(), retry_n8n_execution=AsyncMock(return_value=accepted_receipt())
    )
    if fault == "preflight":
        client.preflight.side_effect = RuntimeError("PRIVATE_KEY")
    if fault == "post_timeout":
        client.retry_n8n_execution.side_effect = TimeoutError("PRIVATE_KEY")
    service = ActionService(config(database_config), client=client)
    if fault in {"mark_audit", "finish_audit"}:
        operation = "mark_dispatch" if fault == "mark_audit" else "finish"

        def fail(*_, **__):
            raise RuntimeError("PRIVATE_KEY")

        monkeypatch.setattr(service.repository, operation, fail)

    async def run():
        try:
            action = await service.plan(*evidence)
            with pytest.raises(StorageError, match="explicit_approval_required"):
                await service.execute(action["id"])
            assert client.preflight.await_count == 0
            result = await service.execute(action["id"], approve_retry_side_effects=True)
            with pytest.raises(StorageError, match="action_already_consumed"):
                await service.execute(action["id"], approve_retry_side_effects=True)
            return result, action["id"]
        finally:
            await service.close()

    result, action_id = asyncio.run(run())
    expected = {
        "none": "ACCEPTED",
        "preflight": "REJECTED",
        "post_timeout": "UNKNOWN",
        "mark_audit": "UNKNOWN",
        "finish_audit": "UNKNOWN",
    }[fault]
    assert result["status"] == expected and "PRIVATE_KEY" not in str(result)
    assert client.retry_n8n_execution.await_count == (
        0 if fault in {"preflight", "mark_audit"} else 1
    )
    stored = ActionRepository(engine).action(action_id)
    assert stored["state"] == ("EXECUTING" if fault in {"mark_audit", "finish_audit"} else expected)
    assert ActionRepository(engine).incident(evidence[0])["status"] == "OPEN"


def test_fixture_actual_retry_client_and_read_only_http_action_history(
    engine, database_config, evidence
):
    settings = config(database_config)
    service = ActionService(settings, client=retry_client(settings))

    async def run():
        try:
            action = await service.plan(*evidence)
            return await service.execute(action["id"], approve_retry_side_effects=True)
        finally:
            await service.close()

    result = asyncio.run(run())
    assert result["status"] == "ACCEPTED" and result["action"]["provider_state"] == "running"
    with TestClient(create_app(settings)) as client:
        assert client.get("/actions").json()["http_execution"] is False
        assert client.get("/actions").json()["approval_required"] is True
        rows = client.get("/history/actions").json()
        assert len(rows) == 1 and rows[0]["state"] == "ACCEPTED"
        assert client.get("/history/actions/" + rows[0]["id"]).json() == rows[0]
        assert client.get("/history/actions?limit=101").status_code == 422
        assert client.get("/history/actions/" + str(uuid4())).status_code == 404
        assert client.post("/actions").status_code == 405
        assert client.post("/history/actions").status_code == 405
        assert client.post(f"/actions/{rows[0]['id']}/execute").status_code == 404
        assert client.get("/tools").json()["policy"]["monitored_system_writes"] is False
        assert len(client.get("/tools").json()["tools"]) == 13


@pytest.mark.parametrize(
    "options",
    [
        {"n8n_retry_mode": "fixture"},
        {"n8n_retry_mode": "fixture", "storage_mode": "local"},
        {
            "n8n_retry_mode": "live",
            "n8n_mode": "live",
            "storage_mode": "local",
            "n8n_retry_workflow_ids": ["wf"],
        },
        {
            "n8n_retry_mode": "fixture",
            "n8n_mode": "fixture",
            "storage_mode": "local",
            "n8n_retry_workflow_ids": [],
        },
        {"n8n_retry_workflow_ids": ["../workflow"]},
        {"n8n_retry_workflow_ids": ["wf", "wf"]},
        {"n8n_retry_mode": "live", "environment": "production"},
    ],
)
def test_retry_configuration_fails_closed(options):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **options)


def test_disabled_actions_and_production_reads_remain_blocked():
    service = ActionService(Settings(_env_file=None))

    async def run():
        try:
            with pytest.raises(StorageError, match="action_disabled"):
                await service.execute(str(uuid4()), approve_retry_side_effects=True)
        finally:
            await service.close()

    asyncio.run(run())
    with TestClient(create_app(Settings(_env_file=None, environment="production"))) as client:
        assert client.get("/actions").status_code == 404
        assert client.get("/history/actions").status_code == 404


def test_provider_calls_follow_committed_approval_and_dispatch_intent(
    engine, database_config, evidence
):
    repository = ActionRepository(engine)
    calls = []

    async def preflight(*_):
        row = repository.actions()[0]
        assert row["state"] == "EXECUTING" and row["approved_at"] is not None
        assert row["dispatch_started_at"] is None
        calls.append("preflight")

    async def post(*_):
        row = repository.actions()[0]
        assert row["state"] == "EXECUTING" and row["dispatch_started_at"] is not None
        calls.append("post")
        return accepted_receipt()

    service = ActionService(
        config(database_config), client=Mock(preflight=preflight, retry_n8n_execution=post)
    )

    async def run():
        try:
            action = await service.plan(*evidence)
            return await service.execute(action["id"], approve_retry_side_effects=True)
        finally:
            await service.close()

    assert asyncio.run(run())["status"] == "ACCEPTED" and calls == ["preflight", "post"]


@pytest.mark.parametrize("stage", ["preflight", "post"])
def test_cancelled_caller_drains_pending_work_and_never_replays(
    engine, database_config, evidence, stage
):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        counts = {"preflight": 0, "post": 0}

        async def preflight(*_):
            counts["preflight"] += 1
            if stage == "preflight":
                entered.set()
                await release.wait()

        async def post(*_):
            counts["post"] += 1
            if stage == "post":
                entered.set()
                await release.wait()
            return accepted_receipt()

        service = ActionService(
            config(database_config), client=Mock(preflight=preflight, retry_n8n_execution=post)
        )
        action = await service.plan(*evidence)
        caller = asyncio.create_task(service.execute(action["id"], approve_retry_side_effects=True))
        try:
            await asyncio.wait_for(entered.wait(), 4)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
            with pytest.raises(StorageError, match="action_busy"):
                await service.execute(action["id"], approve_retry_side_effects=True)
            closing = asyncio.create_task(service.close())
            await asyncio.sleep(0)
            assert not closing.done()
        finally:
            release.set()
            await service.close()
        await closing
        assert counts["post"] == (1 if stage == "post" else 0)
        # A new process/service cannot repeat a consumed intent after cancellation.
        reopened = ActionService(config(database_config))
        try:
            with pytest.raises(StorageError, match="action_already_consumed"):
                await reopened.execute(action["id"], approve_retry_side_effects=True)
        finally:
            await reopened.close()
        return ActionRepository(engine).action(action["id"])

    row = asyncio.run(run())
    assert row["state"] == ("ACCEPTED" if stage == "post" else "REJECTED")
