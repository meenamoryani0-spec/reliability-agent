"""Local operator approval; durable consumption precedes any provider write."""

import asyncio
import hashlib
import threading

from app.actions.adapter import Receipt, retry_client
from app.actions.repository import APPROVAL_WINDOW_SECONDS, ActionRepository
from app.db.database import create_storage_engine
from app.db.migrate import HEAD, current_revision
from app.db.repository import StorageError


def action_policy(config):
    return {
        "mode": config.n8n_retry_mode,
        "actions": ["retry_n8n_execution"],
        "approval_required": True,
        "approval_interface": "local_operator_cli",
        "workflow_allowlist": config.n8n_retry_workflow_ids,
        "approval_window_seconds": APPROVAL_WINDOW_SECONDS,
        "max_dispatches_per_execution": 1,
        "automatic_retry": False,
        "model_execution": False,
        "http_execution": False,
        "load_workflow": False,
        "recovery_verification": False,
    }


class ActionService:
    def __init__(self, config, *, client=None):
        self.config = config
        self.engine = create_storage_engine(config)
        self.repository = ActionRepository(self.engine) if self.engine is not None else None
        self.client = client if client is not None else retry_client(config)
        source = (
            "n8n-fixture-v1"
            if config.n8n_retry_mode == "fixture"
            else config.n8n_base_url or "unconfigured"
        )
        self.source_hash = hashlib.sha256(source.encode()).hexdigest()
        self._slot = threading.Lock()
        self._pending = set()
        self._closed = False

    def _spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    async def _thread(self, function, *args, **kwargs):
        return await asyncio.shield(self._spawn(asyncio.to_thread(function, *args, **kwargs)))

    def _verify(self):
        if self._closed or self.config.environment == "production":
            raise StorageError("action_access_disabled")
        if self.engine is None:
            raise StorageError("storage_disabled")
        try:
            if current_revision(self.engine) != HEAD:
                raise StorageError("migration_required")
        except StorageError:
            raise
        except Exception:
            raise StorageError("storage_unavailable") from None

    def _enabled(self):
        if self.config.n8n_retry_mode == "disabled" or self.client is None:
            raise StorageError("action_disabled")

    def _policy(self):
        return {
            "source_hash": self.source_hash,
            "mode": self.config.n8n_retry_mode,
            "allowed": self.config.n8n_retry_workflow_ids,
        }

    async def plan(self, incident_id, check_id):
        self._enabled()

        async def plan():
            await self._thread(self._verify)
            return await self._thread(
                self.repository.propose, incident_id, check_id, **self._policy()
            )

        return await asyncio.shield(self._spawn(plan()))

    async def inspect(self, action_id):
        async def read():
            await self._thread(self._verify)
            return await self._thread(self.repository.action, action_id)

        return await asyncio.shield(self._spawn(read()))

    async def execute(self, action_id, *, approve_retry_side_effects=False):
        self._enabled()
        if approve_retry_side_effects is not True:
            raise StorageError("explicit_approval_required")
        await self._thread(self._verify)
        if self._closed:
            raise StorageError("action_access_disabled")
        if not self._slot.acquire(blocking=False):
            raise StorageError("action_busy")
        return await asyncio.shield(self._spawn(self._execute(action_id)))

    async def _execute(self, action_id):
        try:
            # This commit consumes approval globally before any provider I/O.
            action = await self._thread(self.repository.claim, action_id, **self._policy())
            receipt, dispatched = None, False
            if self._closed:
                return await self._finish(action, None, False)
            try:
                await self.client.preflight(action["execution_id"], action["workflow_id"])
            except Exception:
                return await self._finish(action, None, False)
            if self._closed:
                return await self._finish(action, None, False)
            # If recording dispatch intent fails, do not send the write.
            try:
                await self._thread(self.repository.mark_dispatch, action_id)
            except Exception:
                return self._unknown(action, None, False)
            dispatched = True
            try:
                raw = await self.client.retry_n8n_execution(
                    action["execution_id"], action["workflow_id"]
                )
                receipt = Receipt.model_validate(raw.model_dump())
                if (
                    receipt.id == action["execution_id"]
                    or receipt.retryOf != action["execution_id"]
                    or receipt.workflowId != action["workflow_id"]
                ):
                    receipt = None
            except Exception:
                receipt = None
            return await self._finish(action, receipt, dispatched)
        finally:
            self._slot.release()

    async def _finish(self, action, receipt, dispatched):
        try:
            row = await self._thread(
                self.repository.finish, action["id"], receipt=receipt, dispatched=dispatched
            )
            return {"status": row["state"], "durable_outcome": True, "action": row}
        except Exception:
            # Keep the consumed intent blocked, even when a receipt cannot be saved.
            return self._unknown(action, receipt, dispatched)

    @staticmethod
    def _unknown(action, receipt, dispatched):
        return {
            "status": "UNKNOWN",
            "durable_outcome": False,
            "action_id": action["id"],
            "reason": "audit_unavailable",
            "new_execution_id": receipt.id if receipt else None,
            "provider_submission": "accepted"
            if receipt
            else "unknown"
            if dispatched
            else "not_sent",
            "recovery_verified": False,
            "business_outcome_verified": False,
        }

    async def close(self):
        self._closed = True
        if self._pending:
            await asyncio.gather(
                *(asyncio.shield(task) for task in tuple(self._pending)), return_exceptions=True
            )
        if self.engine is not None:
            await asyncio.to_thread(self.engine.dispose)
