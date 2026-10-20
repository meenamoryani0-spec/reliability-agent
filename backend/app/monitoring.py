"""Operator-managed targets. Registration never executes a check or an AI tool."""

import asyncio
import hashlib

from sqlalchemy import JSON, String, select, text
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from app.db.models import Base
from app.db.repository import StorageError
from app.tools.models import WebsiteTarget


class WebsiteCheckBusy(Exception):
    pass


class SavedWebsiteTarget(Base):
    __tablename__ = "website_targets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    configuration: Mapped[dict] = mapped_column(JSON)


class WebsiteTargets:
    def __init__(self, config, history):
        self.history = history
        self.seeds = {target.id: target for target in config.website_targets}
        self.cached = dict(self.seeds)
        self.pending = set()
        self.closed = False
        self.check_busy = False

    async def _call(self, target=None):
        if self.closed:
            raise StorageError("storage_unavailable")
        task = asyncio.create_task(asyncio.to_thread(self._sync, target))
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)
        targets = await asyncio.shield(task)
        self.cached.clear()
        self.cached.update(targets)
        return targets

    def _sync(self, target):
        engine = self.history.engine
        if engine is None:
            if target is not None:
                raise StorageError("storage_disabled")
            return dict(self.seeds)
        if not self.history.verify():
            raise StorageError("storage_unavailable")
        try:
            with sessionmaker(engine).begin() as session:
                if target is not None:
                    if engine.dialect.name == "sqlite":
                        session.connection(execution_options={"sqlite_write": True})
                    else:
                        # Serialize the bounded target count across concurrent registrations.
                        session.execute(text("SELECT pg_advisory_xact_lock(731924106)"))
                targets = dict(self.seeds)
                for row in session.scalars(select(SavedWebsiteTarget).limit(26)):
                    value = WebsiteTarget.model_validate(row.configuration)
                    if value.id != row.id or row.id in self.seeds:
                        raise StorageError("target_configuration_conflict")
                    targets[value.id] = value
                if len(targets) > 25:
                    raise StorageError("target_limit_reached")
                if target is not None and not any(t.url == target.url for t in targets.values()):
                    if len(targets) >= 25:
                        raise StorageError("target_limit_reached")
                    if target.id in targets:
                        raise StorageError("target_configuration_conflict")
                    session.add(
                        SavedWebsiteTarget(
                            id=target.id, configuration=target.model_dump(mode="json")
                        )
                    )
                    targets[target.id] = target
            return targets
        except StorageError:
            raise
        except Exception:
            raise StorageError("storage_unavailable") from None

    async def all(self):
        return await self._call()

    async def get(self, identifier):
        return (await self.all()).get(identifier)

    async def add(self, url):
        identifier = "site-" + hashlib.sha256(url.encode()).hexdigest()[:24]
        target = WebsiteTarget(id=identifier, url=url)
        targets = await self._call(target)
        return next(value for value in targets.values() if value.url == target.url)

    async def check(self, target, checker, *, on_capture=None):
        if self.closed:
            raise StorageError("storage_unavailable")
        if self.check_busy:
            raise WebsiteCheckBusy()
        self.check_busy = True

        async def run():
            try:
                results = []
                for operation in (checker.check_http, checker.check_dns, checker.check_ssl):
                    result = await operation(target)
                    saved = await self.history.capture(result, target.url)
                    if on_capture is not None:
                        on_capture(saved)
                    results.append(
                        {
                            "check": result.model_dump(mode="json"),
                            "history": saved.model_dump(mode="json"),
                        }
                    )
                return {"results": results, "automatic_monitoring": False}
            finally:
                self.check_busy = False

        task = asyncio.create_task(run())
        self.pending.add(task)

        def finished(value):
            self.pending.discard(value)
            if not value.cancelled():
                value.exception()

        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def close(self):
        self.closed = True
        if self.pending:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self.pending)))
