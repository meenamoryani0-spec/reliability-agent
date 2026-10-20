import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.db.service import HistoryService
from app.main import create_app
from app.monitoring import WebsiteCheckBusy, WebsiteTargets
from app.tools.models import CheckResult, WebsiteTarget
from app.website_schedule import WebsiteSchedule


def config(database_config, **options):
    return Settings(
        _env_file=None,
        **{
            **database_config.model_dump(),
            "environment": "test",
            "website_monitoring_enabled": True,
            "website_targets": [WebsiteTarget(id="site", url="https://example.com/")],
            **options,
        },
    )


def checker():
    value = AsyncMock()
    for method, kind in (("check_http", "http"), ("check_dns", "dns"), ("check_ssl", "ssl")):

        async def check(target, kind=kind):
            return CheckResult(
                component=target.id,
                check_type=kind,
                status="UNHEALTHY" if kind == "http" else "HEALTHY",
                summary="Controlled test result",
            )

        getattr(value, method).side_effect = check
    return value


@pytest.mark.parametrize("interval", [0, 59, 86401])
def test_schedule_interval_is_bounded(interval):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, website_monitoring_interval_seconds=interval)


def test_schedule_is_opt_in_and_requires_history_and_authorized_production_access():
    adapter = checker()
    with TestClient(create_app(Settings(_env_file=None), website_checker=adapter)) as client:
        status = client.get("/monitoring").json()
        assert status["automatic_monitoring"] is False
        assert status["website_schedule"]["state"] == "disabled"
        assert status["website_schedule"]["cycles_started"] == 0
        adapter.check_http.assert_not_awaited()
    with pytest.raises(ValidationError):
        Settings(_env_file=None, website_monitoring_enabled=True)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            storage_mode="postgresql",
            website_monitoring_enabled=True,
        )


def test_saved_targets_are_reloaded_and_repeated_failures_reuse_incident(database_config, engine):
    async def run():
        settings = config(database_config, incidents_enabled=True)
        history = HistoryService(settings)
        targets = WebsiteTargets(settings, history)
        adapter = checker()
        schedule = WebsiteSchedule(settings, targets, adapter, history)
        try:
            await schedule._cycle()
            await schedule._cycle()
            rows = await history.read("incidents")
            assert len(rows) == 1 and rows[0]["observation_count"] == 2
            assert rows[0]["root_cause_verified"] is False
            assert len(await history.read("checks")) == 6
            await targets.add("https://example.com/second")
            await schedule._cycle()
            assert schedule.last_checks_saved == 6
            assert len(await history.read("incidents")) == 2

            async def healthy(target):
                return CheckResult(
                    component=target.id, check_type="http", status="HEALTHY", summary="Healthy"
                )

            adapter.check_http.side_effect = healthy
            await schedule._cycle()
            assert all(row["status"] == "OPEN" for row in await history.read("incidents"))
        finally:
            await schedule.close()
            await targets.close()
            await history.close()

    asyncio.run(run())


def test_storage_failure_and_occupied_manual_slot_do_not_run_checks(database_config, engine):
    async def run():
        settings = config(database_config)
        history = HistoryService(settings)
        targets = WebsiteTargets(settings, history)
        adapter = checker()
        schedule = WebsiteSchedule(settings, targets, adapter, history)
        try:
            actual_readiness = history.readiness
            history.readiness = AsyncMock(return_value=False)
            await schedule._cycle()
            assert schedule.last_outcome == "storage_unavailable"
            adapter.check_http.assert_not_awaited()
            history.readiness = actual_readiness
            targets.check_busy = True
            await schedule._cycle()
            assert schedule.last_outcome == "busy"
            adapter.check_http.assert_not_awaited()
            targets.check_busy = False
            await schedule._cycle()
            assert schedule.last_outcome == "completed" and schedule.last_checks_saved == 3
            assert await history.read("incidents") == []
        finally:
            await schedule.close()
            await targets.close()
            await history.close()

    asyncio.run(run())


def test_timer_repeats_without_overlap_and_shutdown_drains_current_batch(database_config, engine):
    async def run():
        settings = config(database_config)
        history = HistoryService(settings)
        targets = WebsiteTargets(settings, history)
        adapter = checker()
        schedule = WebsiteSchedule(settings, targets, adapter, history)
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def http(target):
            nonlocal calls
            calls += 1
            if calls == 2:
                entered.set()
                await release.wait()
            return CheckResult(
                component=target.id, check_type="http", status="HEALTHY", summary="Test"
            )

        adapter.check_http.side_effect = http
        # Accelerate only the test timer; production configuration rejects this interval.
        schedule.interval = 0.01
        try:
            schedule.start()
            schedule.start()
            await asyncio.wait_for(entered.wait(), timeout=5)
            with pytest.raises(WebsiteCheckBusy):
                await targets.check(settings.website_targets[0], adapter)
            closing = asyncio.create_task(schedule.close())
            await asyncio.sleep(0)
            assert not closing.done() and targets.check_busy
            release.set()
            await asyncio.wait_for(closing, timeout=5)
            assert calls == 2 and schedule.cycles_started == 2
            assert schedule.state == "stopped" and not targets.check_busy
            assert len(await history.read("checks")) == 6
        finally:
            release.set()
            await schedule.close()
            await targets.close()
            await history.close()

    asyncio.run(run())


def test_probe_exception_is_sanitized_and_next_cycle_recovers(database_config, engine, caplog):
    async def run():
        settings = config(database_config)
        history = HistoryService(settings)
        targets = WebsiteTargets(settings, history)
        adapter = checker()
        schedule = WebsiteSchedule(settings, targets, adapter, history)
        try:
            adapter.check_dns.side_effect = RuntimeError("sentinel-private-error")
            await schedule._cycle()
            assert schedule.last_outcome == "failed"
            assert schedule.last_checks_saved == 1
            assert not targets.check_busy
            assert "sentinel-private-error" not in str(schedule.describe()) + caplog.text
            adapter = checker()
            schedule.checker = adapter
            await schedule._cycle()
            assert schedule.last_outcome == "completed" and schedule.last_checks_saved == 3
        finally:
            await schedule.close()
            await targets.close()
            await history.close()

    asyncio.run(run())
