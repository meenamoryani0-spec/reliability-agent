"""Exercise the registry using actual Chromium and isolated local fixture history."""

import asyncio
import json
import tempfile
from pathlib import Path

from app.agent.tool_registry import ToolRegistry
from app.config import PROJECT_ROOT, Settings
from app.db.migrate import upgrade
from app.db.service import HistoryService
from app.tools.browser import BrowserChecker
from app.tools.infrastructure import InfrastructureService
from app.tools.n8n import N8nService
from app.tools.n8n_fixtures import fixture_client
from app.tools.website import WebsiteChecker


async def main():
    scratch = PROJECT_ROOT / "work" / "tool-smoke"
    scratch.mkdir(parents=True, exist_ok=True)
    database = Path(tempfile.mkdtemp(prefix="run-", dir=scratch)) / "history.sqlite3"
    config = Settings(
        _env_file=None,
        environment="test",
        website_targets=[],
        n8n_mode="fixture",
        infrastructure_mode="fixture",
        nebius_api_key=None,
        n8n_api_key=None,
        vercel_token=None,
        supabase_access_token=None,
        postgres_password=None,
        storage_database_url=None,
        storage_mode="local",
        storage_allow_loopback=False,
        storage_sqlite_file=str(database.relative_to(PROJECT_ROOT)),
    )
    history = HistoryService(config)
    upgrade(history.engine)  # Explicit migration of this new scratch database only.
    registry = ToolRegistry(
        config,
        website_checker=WebsiteChecker(),
        browser_checker=BrowserChecker(),
        n8n_service=N8nService("fixture", fixture_client()),
        infrastructure_service=InfrastructureService(config),
        history=history,
    )
    calls = [
        ("list_website_targets", {}, None),
        ("list_n8n_workflows", {}, None),
        ("list_failed_n8n_executions", {"workflow_id": "wf-booking"}, None),
        ("get_n8n_execution", {"execution_id": "1001"}, "UNHEALTHY"),
        ("get_n8n_execution", {"execution_id": "1002"}, "HEALTHY"),
        ("check_vercel_deployment", {}, "UNHEALTHY"),
        ("get_vercel_deployment_events", {}, "UNKNOWN"),
        ("check_supabase_project", {}, "HEALTHY"),
        ("check_supabase_health", {}, "HEALTHY"),
        ("check_postgres", {}, "HEALTHY"),
        ("test_website_flow", {"flow_id": "booking-healthy"}, "HEALTHY"),
        ("test_website_flow", {"flow_id": "booking-crm-failure"}, "UNHEALTHY"),
    ]
    results = []
    try:
        for name, arguments, status in calls:
            result = await registry.execute(name, json.dumps(arguments))
            if result.status != "OK":
                raise RuntimeError("Registry fixture dispatch failed")
            if status and (
                result.data["status"] != status
                or result.data["synthetic"] is not True
                or result.history.status != "saved"
                or result.data["root_cause_verified"]
                or result.data["business_outcome_verified"]
            ):
                raise RuntimeError("Unexpected fixture observation or history result")
            results.append(result.model_dump(mode="json"))
        for name, arguments in [
            ("retry_n8n_execution", "{}"),
            ("check_postgres", '{"sql":"SELECT arbitrary"}'),
            ("check_dns", '{"target_id":"unregistered"}'),
        ]:
            if (await registry.execute(name, arguments)).status != "REJECTED":
                raise RuntimeError("Registry failed to reject an unauthorized operation")
        checks = await history.read("checks", limit=100)
        services = await history.read("services", limit=100)
        incidents = await history.read("incidents", limit=100)
        if len(checks) != 9 or len(services) != 8 or incidents:
            raise RuntimeError("Unexpected fixture history or automatic incident")
        evidence = {
            "result": "PASS",
            "catalog_tools": len(registry.definitions()),
            "distinct_tools_executed": len({call[0] for call in calls}),
            "calls_completed": len(results),
            "checks_persisted": len(checks),
            "services_persisted": len(services),
            "automatic_incidents": len(incidents),
            "provider_data": "synthetic_fixtures",
            "browser": "real_chromium_with_intercepted_fixtures",
            "live_providers_verified": False,
            "calls": results,
        }
        directory = PROJECT_ROOT / "work" / "evidence"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "phase-8-tools-smoke.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        print(json.dumps({key: value for key, value in evidence.items() if key != "calls"}))
    finally:
        await registry.close()
        await history.close()


if __name__ == "__main__":
    asyncio.run(main())
