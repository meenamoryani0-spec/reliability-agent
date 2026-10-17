"""Persist actual backend fixture results and verify them after a server restart."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from smoke_support import server

ROOT = Path(__file__).resolve().parents[1]
HIDDEN = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def main():
    identifier = uuid4().hex
    data_file = f"work/data/storage-smoke-{identifier}.sqlite3"
    environment = {
        **os.environ,
        "ENVIRONMENT": "test",
        "N8N_RETRY_MODE": "disabled",
        "N8N_RETRY_WORKFLOW_IDS": "[]",
        "LOG_LEVEL": "INFO",
        "INCIDENTS_ENABLED": "false",
        "INVESTIGATION_MODE": "disabled",
        "STORAGE_MODE": "local",
        "STORAGE_SQLITE_FILE": data_file,
        "STORAGE_DATABASE_URL": "",
        "STORAGE_ALLOW_LOOPBACK": "false",
        "N8N_MODE": "fixture",
        "N8N_BASE_URL": "",
        "N8N_API_KEY": "",
        "N8N_DNS_NAMESERVERS": "[]",
        "INFRASTRUCTURE_MODE": "fixture",
        "INFRASTRUCTURE_DNS_NAMESERVERS": "[]",
        "INFRASTRUCTURE_TIMEOUT_SECONDS": "10",
        "NEBIUS_API_KEY": "",
        "WEBSITE_TARGETS": "[]",
        "VERCEL_TOKEN": "",
        "VERCEL_DEPLOYMENT_ID": "",
        "VERCEL_TEAM_ID": "",
        "SUPABASE_ACCESS_TOKEN": "",
        "SUPABASE_PROJECT_REF": "",
        "POSTGRES_HOST": "",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DBNAME": "",
        "POSTGRES_USER": "",
        "POSTGRES_PASSWORD": "",
    }
    migration = subprocess.run(
        [sys.executable, "-m", "app.db.cli", "upgrade"],
        cwd=ROOT / "backend",
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        creationflags=HIDDEN,
    )
    if migration.returncode != 0:
        raise RuntimeError("Storage smoke migration failed")
    log_dir = ROOT / "work" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with server(environment, log_dir / "storage-before-restart.log") as client:
        paths = [
            ("POST", "/checks/infrastructure/" + name)
            for name in (
                "vercel-deployment",
                "vercel-events",
                "supabase-project",
                "supabase-health",
                "postgres",
            )
        ]
        paths += [("GET", "/n8n/executions/" + name) for name in ("1001", "1002")]
        paths += [
            ("POST", "/checks/browser-flows/" + name)
            for name in ("booking-healthy", "booking-crm-failure")
        ]
        ids = set()
        for method, path in paths:
            response = client.request(method, path, timeout=45)
            response.raise_for_status()
            if response.headers.get("x-history-status") != "saved":
                raise RuntimeError("Backend check result was not persisted")
            ids.add(response.headers["x-check-id"])
        history = client.get("/history/checks?limit=100").json()
        if len(history) != 9 or {row["id"] for row in history} != ids:
            raise RuntimeError("Unexpected stored check history")
        if client.get("/history/incidents").json() != []:
            raise RuntimeError("Disabled detection must not create incidents automatically")
    with server(environment, log_dir / "storage-after-restart.log") as client:
        recovered = client.get("/history/checks?limit=100").json()
        if {row["id"] for row in recovered} != ids:
            raise RuntimeError("History did not survive backend restart")
        if "SYNTHETIC_PRIVATE_DATA_DO_NOT_RETURN" in json.dumps(recovered):
            raise RuntimeError("Private fixture data reached history")
        services = client.get("/history/services?limit=100").json()
        if len(services) != 8 or not all(row["synthetic"] for row in services):
            raise RuntimeError("Unexpected service identities or synthetic flags")
    result = {
        "result": "PASS",
        "checks_persisted": len(ids),
        "services_persisted": len(services),
        "backend_restart_verified": True,
        "automatic_incidents": 0,
        "storage": "local_sqlite_file",
        "provider_data": "synthetic_fixtures",
    }
    (ROOT / "work" / "evidence").mkdir(parents=True, exist_ok=True)
    (ROOT / "work" / "evidence" / "phase-7-storage-smoke.json").write_text(
        json.dumps(result, indent=2)
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
