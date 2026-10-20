"""Opt-in website checks while this single backend process remains running."""

import asyncio
import logging
from datetime import UTC, datetime

from app.monitoring import WebsiteCheckBusy

logger = logging.getLogger("reliability_agent")


class WebsiteSchedule:
    def __init__(self, config, targets, checker, history):
        self.enabled = config.website_monitoring_enabled
        self.interval = config.website_monitoring_interval_seconds
        self.targets = targets
        self.checker = checker
        self.history = history
        self.state = "starting" if self.enabled else "disabled"
        self.last_started_at = None
        self.last_finished_at = None
        self.last_outcome = None
        self.last_checks_saved = 0
        self.cycles_started = 0
        self._stop = asyncio.Event()
        self._task = None
        self._closed = False

    def describe(self):
        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval,
            "state": self.state,
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "last_outcome": self.last_outcome,
            "last_checks_saved": self.last_checks_saved,
            "cycles_started": self.cycles_started,
            "coverage": "registered_websites_while_backend_running",
        }

    def start(self):
        if self.enabled and self._task is None and not self._closed:
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        while not self._stop.is_set():
            await self._cycle()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except TimeoutError:
                pass

    async def _cycle(self):
        self.cycles_started += 1
        self.state = "checking"
        self.last_started_at = datetime.now(UTC).isoformat()
        self.last_checks_saved = 0
        self.last_outcome = "completed"

        def captured(saved):
            if saved.status == "saved":
                self.last_checks_saved += 1

        try:
            if not await self.history.readiness():
                self.last_outcome = "storage_unavailable"
                return
            targets = await self.targets.all()
            if not targets:
                self.last_outcome = "no_targets"
            for target in targets.values():
                if self._stop.is_set():
                    self.last_outcome = "stopped"
                    break
                try:
                    result = await self.targets.check(target, self.checker, on_capture=captured)
                except WebsiteCheckBusy:
                    self.last_outcome = "busy"
                    break
                saved = sum(item["history"]["status"] == "saved" for item in result["results"])
                if saved != 3:
                    self.last_outcome = "partial"
        except Exception:
            self.last_outcome = "failed"
            logger.warning("Scheduled website checks could not finish")
        finally:
            self.last_finished_at = datetime.now(UTC).isoformat()
            self.state = "stopping" if self._stop.is_set() else "waiting"

    async def close(self):
        self._closed = True
        self._stop.set()
        if self._task is not None:
            await asyncio.shield(self._task)
        self.state = "stopped" if self.enabled else "disabled"
