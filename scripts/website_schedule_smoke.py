"""Actual loopback HTTP and scratch storage; website probes are controlled fixtures."""

import json
import os
import time
from uuid import uuid4

from smoke_support import ROOT, server


def create_test_app():
    from app.config import Settings
    from app.db.database import create_storage_engine
    from app.db.migrate import upgrade
    from app.main import create_app
    from app.tools.models import CheckResult, WebsiteTarget

    class ControlledChecker:
        async def check_http(self, target):
            return CheckResult(
                component=target.id,
                check_type="http",
                status="UNHEALTHY",
                summary="Controlled local fixture; not provider verification",
                evidence={"http_status": 500},
            )

        async def check_dns(self, target):
            return CheckResult(
                component=target.id, check_type="dns", status="HEALTHY", summary="Test fixture"
            )

        async def check_ssl(self, target):
            return CheckResult(
                component=target.id, check_type="ssl", status="HEALTHY", summary="Test fixture"
            )

    config = Settings(
        _env_file=None,
        website_targets=[WebsiteTarget(id="schedule-test", url="https://example.com/")],
    )
    engine = create_storage_engine(config)
    upgrade(engine)
    engine.dispose()
    return create_app(config, website_checker=ControlledChecker())


def main():
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "scripts"),
        "ENVIRONMENT": "test",
        "STORAGE_MODE": "local",
        "STORAGE_SQLITE_FILE": f"work/schedule-smoke/{uuid4().hex}.sqlite3",
        "STORAGE_DATABASE_URL": "",
        "API_ACCESS_TOKEN": "",
        "API_ALLOWED_HOSTS": "[]",
        "WEBSITE_TARGETS": "[]",
        "WEBSITE_MONITORING_ENABLED": "true",
        "WEBSITE_MONITORING_INTERVAL_SECONDS": "300",
        "INCIDENTS_ENABLED": "true",
        "INVESTIGATION_MODE": "disabled",
        "N8N_MODE": "disabled",
        "N8N_EVENTS_ENABLED": "false",
        "N8N_RETRY_MODE": "disabled",
        "N8N_RECOVERY_MODE": "disabled",
        "INFRASTRUCTURE_MODE": "disabled",
    }
    log = ROOT / "work/logs/website-schedule-smoke.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with server(
        environment, log, application="website_schedule_smoke:create_test_app", factory=True
    ) as client:
        deadline = time.monotonic() + 15
        while True:
            response = client.get("/monitoring")
            response.raise_for_status()
            schedule = response.json()["website_schedule"]
            if schedule["last_finished_at"] is not None:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Scheduled scan did not finish")
            time.sleep(0.1)
        assert schedule["enabled"] and schedule["last_checks_saved"] == 3
        assert schedule["last_outcome"] == "completed"
        checks = client.get("/history/checks").json()
        incidents = client.get("/history/incidents").json()
        assert len(checks) == 3 and len(incidents) == 1
        assert incidents[0]["status"] == "OPEN"
        assert incidents[0]["root_cause_verified"] is False
    evidence = ROOT / "work/evidence/website-schedule-smoke.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "result": "PASS",
        "actual_loopback_http": True,
        "website_probes": "controlled_local_fixtures",
        "checks_saved": 3,
        "open_incidents": 1,
        "live_provider_or_ai_validation": False,
    }
    evidence.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
