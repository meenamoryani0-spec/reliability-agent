import asyncio
import logging

from sqlalchemy.exc import SQLAlchemyError

from app.db.assessment import AssessmentCapture
from app.db.capture import HistoryCapture, IncidentCapture
from app.db.database import create_storage_engine
from app.db.migrate import HEAD, current_revision
from app.db.repository import HistoryRepository, StorageError
from app.db.snapshots import snapshot_for

logger = logging.getLogger("reliability_agent")


class HistoryService:
    def __init__(self, config):
        self.mode = config.storage_mode
        self.incidents_enabled = config.incidents_enabled
        self.engine = create_storage_engine(config)
        self.repository = HistoryRepository(self.engine) if self.engine is not None else None
        self.state = "disabled" if self.engine is None else "not_verified"
        self._pending = set()
        self._closed = False

    def describe(self):
        return {
            "mode": self.mode,
            "state": self.state,
            "expected_revision": HEAD,
            "automatic_incidents": self.incidents_enabled,
            "incident_policy": "persisted_unhealthy_by_service_and_kind",
            "incident_resolution": False,
        }

    def verify(self):
        if self.engine is None:
            return False
        try:
            self.state = "ready" if current_revision(self.engine) == HEAD else "migration_required"
        except SQLAlchemyError:
            self.state = "unavailable"
        return self.state == "ready"

    async def capture(self, result, source):
        # A single tracked worker completes both stages even if its caller is cancelled.
        if self._closed:
            return HistoryCapture(
                status="unavailable",
                incident=IncidentCapture(
                    status="unavailable" if self.incidents_enabled else "disabled"
                ),
            )
        task = asyncio.create_task(asyncio.to_thread(self._capture_sync, result, source))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return await asyncio.shield(task)

    def _capture_sync(self, result, source):
        incident = IncidentCapture(status="unavailable" if self.incidents_enabled else "disabled")
        if self.repository is None and not self.incidents_enabled:
            return HistoryCapture(status="disabled", incident=incident)
        try:
            snapshot = snapshot_for(result, source)
            if snapshot.status != "UNHEALTHY" and self.incidents_enabled:
                incident = IncidentCapture(status="not_applicable")
            if self.repository is None:
                return HistoryCapture(status="disabled", incident=incident)
            if not self.verify():
                return HistoryCapture(status="unavailable", incident=incident)
            # Commit check history first; incident failure must not roll it back.
            identifier = self.repository.record(snapshot)
        except Exception:
            self.state = "unavailable"
            logger.warning("Check history could not be saved")
            return HistoryCapture(status="unavailable", incident=incident)
        if self.incidents_enabled and snapshot.status == "UNHEALTHY":
            try:
                row, created = self.repository.ensure_incident(identifier)
                incident = IncidentCapture(
                    status="created" if created else "existing", incident_id=row["id"]
                )
            except Exception:
                logger.warning("Incident detection could not be saved")
                incident = IncidentCapture(status="unavailable")
        return HistoryCapture(status="saved", check_id=identifier, incident=incident)

    async def read(self, operation, **kwargs):
        if self.repository is None:
            raise StorageError("storage_disabled")
        if operation not in {
            "services",
            "checks",
            "check",
            "incidents",
            "incident",
            "incident_observations",
            "incident_assessments",
            "actions",
            "action",
            "verifications",
            "verification",
        }:
            raise ValueError("Unsupported history operation")
        if not await asyncio.to_thread(self.verify):
            raise StorageError("storage_unavailable")
        return await asyncio.to_thread(getattr(self.repository, operation), **kwargs)

    async def save_assessments(self, drafts):
        if not self.incidents_enabled:
            return AssessmentCapture(status="disabled")
        if not drafts:
            return AssessmentCapture()
        if self._closed:
            return AssessmentCapture(status="unavailable")
        task = asyncio.create_task(asyncio.to_thread(self._save_assessments_sync, drafts))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return await asyncio.shield(task)

    def _save_assessments_sync(self, drafts):
        try:
            if self.repository is None or not self.verify():
                return AssessmentCapture(status="unavailable")
            identifiers = self.repository.save_assessments(drafts)
            return AssessmentCapture(status="saved", check_ids=identifiers)
        except Exception:
            logger.warning("Incident assessment could not be saved")
            return AssessmentCapture(status="unavailable")

    async def close(self):
        self._closed = True
        if self._pending:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._pending)))
        if self.engine is not None:
            await asyncio.to_thread(self.engine.dispose)
