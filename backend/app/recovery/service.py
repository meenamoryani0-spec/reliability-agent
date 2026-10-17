"""One bounded read per operator call; no provider writes, polling or model approval."""

import asyncio
import hashlib
import threading

from app.db.database import create_storage_engine
from app.db.migrate import HEAD, current_revision
from app.db.models import now
from app.db.repository import StorageError
from app.db.snapshots import snapshot_for
from app.recovery.reader import read_execution
from app.recovery.repository import RecoveryRepository
from app.tools.n8n_models import N8nReadResult


def recovery_policy(config):
    return {
        "mode": config.n8n_recovery_mode,
        "interface": "local_operator_cli",
        "flows": {key: value.model_dump() for key, value in config.n8n_recovery_flows.items()},
        "scope": "n8n_required_nodes",
        "business_outcome_verified": False,
        "provider_writes": False,
        "automatic_polling": False,
        "http_verification": False,
        "model_verification": False,
    }


class RecoveryService:
    def __init__(self, config, *, reader=read_execution):
        self.config = config
        self.engine = create_storage_engine(config)
        self.repository = RecoveryRepository(self.engine) if self.engine is not None else None
        self.reader = reader
        self.source = (
            "n8n-fixture-v1"
            if config.n8n_recovery_mode == "fixture"
            else (config.n8n_base_url or "unconfigured")
        )
        self._slot = threading.Lock()
        self._pending, self._closed = set(), False

    def _spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    async def _thread(self, function, *args, **kwargs):
        return await asyncio.shield(self._spawn(asyncio.to_thread(function, *args, **kwargs)))

    def _verify(self):
        if self._closed or self.config.environment == "production":
            raise StorageError("recovery_access_disabled")
        if self.engine is None:
            raise StorageError("storage_disabled")
        try:
            if current_revision(self.engine) != HEAD:
                raise StorageError("migration_required")
        except StorageError:
            raise
        except Exception:
            raise StorageError("storage_unavailable") from None

    async def close(self):
        self._closed = True
        if self._pending:
            await asyncio.gather(
                *(asyncio.shield(task) for task in tuple(self._pending)), return_exceptions=True
            )
        if self.engine is not None:
            await asyncio.to_thread(self.engine.dispose)

    def _policy(self):
        return {
            "source_hash": hashlib.sha256(self.source.encode()).hexdigest(),
            "mode": self.config.n8n_recovery_mode,
            "flows": self.config.n8n_recovery_flows,
        }

    async def verify(self, action_id):
        if self.config.n8n_recovery_mode == "disabled":
            raise StorageError("recovery_disabled")
        await self._thread(self._verify)
        if self._closed:
            raise StorageError("recovery_access_disabled")
        if not self._slot.acquire(blocking=False):
            raise StorageError("recovery_busy")
        return await asyncio.shield(self._spawn(self._run_verification(action_id)))

    async def _run_verification(self, action_id):
        try:
            context = await self._thread(self.repository.prepare, action_id, **self._policy())
            if context["proof"]:
                return self._result(context["proof"], True)
            observed_at, check_id = now(), None
            try:
                result = await asyncio.wait_for(self.reader(self.config, context["action"]), 40)
                result = N8nReadResult.model_validate(result.model_dump())
                if result.synthetic != (self.config.n8n_recovery_mode == "fixture"):
                    raise ValueError("Provenance mismatch")
            except Exception:
                result = None
            if result is not None:
                observed_at = result.checked_at
                # Saving the read is a separate commit. Failure here must never resolve.
                check_id = await self._thread(
                    self.repository.record, snapshot_for(result, self.source)
                )
            try:
                proof, reused = await self._thread(
                    self.repository.finish_verification,
                    action_id,
                    check_id,
                    context["policy"],
                    observed_at,
                    **self._policy(),
                )
            except StorageError as error:
                return {
                    "status": "INCONCLUSIVE",
                    "reason": error.code,
                    "durable_outcome": False,
                    "check_id": check_id,
                    "recovery_verified": False,
                    "business_outcome_verified": False,
                }
            return self._result(proof, reused)
        finally:
            self._slot.release()

    @staticmethod
    def _result(proof, reused):
        return {
            "status": proof["result"],
            "durable_outcome": True,
            "historical_proof_reused": reused,
            "verification": proof,
        }
