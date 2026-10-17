import asyncio
import logging

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import create_storage_engine
from app.db.migrate import HEAD, current_revision
from app.db.repository import HistoryRepository, StorageError
from app.db.snapshots import snapshot_for

logger = logging.getLogger("reliability_agent")


class HistoryService:
    def __init__(self, config):
        self.mode = config.storage_mode
        self.engine = create_storage_engine(config)
        self.repository = HistoryRepository(self.engine) if self.engine is not None else None
        self.state = "disabled" if self.engine is None else "not_verified"

    def describe(self):
        return {
            "mode": self.mode,
            "state": self.state,
            "expected_revision": HEAD,
            "automatic_incidents": False,
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
        if self.repository is None:
            return "disabled", None
        try:
            snapshot = snapshot_for(result, source)
            if not await asyncio.to_thread(self.verify):
                return "unavailable", None
            identifier = await asyncio.to_thread(self.repository.record, snapshot)
            return "saved", identifier
        except (ValueError, ValidationError):
            self.state = "unavailable"
            # Storage exceptions and provider evidence never appear in logs.
            logger.warning("Check history could not be saved")
            return "unavailable", None

    async def read(self, operation, **kwargs):
        if self.repository is None:
            raise StorageError("storage_disabled")
        if operation not in {"services", "checks", "check", "incidents"}:
            raise ValueError("Unsupported history operation")
        if not await asyncio.to_thread(self.verify):
            raise StorageError("storage_unavailable")
        return await asyncio.to_thread(getattr(self.repository, operation), **kwargs)

    async def close(self):
        if self.engine is not None:
            await asyncio.to_thread(self.engine.dispose)
