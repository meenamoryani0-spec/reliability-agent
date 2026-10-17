"""Isolated local frontend fixtures and supervised loopback Next.js process."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from uuid import uuid4

import httpx
from smoke_support import HIDDEN, ROOT


def fixture_environment():
    return {
        **os.environ,
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "INFO",
        "STORAGE_MODE": "local",
        "STORAGE_SQLITE_FILE": f"work/data/frontend-fixture-{uuid4().hex}.sqlite3",
        "STORAGE_DATABASE_URL": "",
        "STORAGE_ALLOW_LOOPBACK": "false",
        "INCIDENTS_ENABLED": "true",
        "INVESTIGATION_MODE": "fixture",
        "NEBIUS_API_KEY": "",
        "N8N_MODE": "fixture",
        "N8N_RETRY_MODE": "fixture",
        "N8N_RETRY_WORKFLOW_IDS": '["wf-booking"]',
        "N8N_RECOVERY_MODE": "fixture",
        "N8N_RECOVERY_FLOWS": json.dumps(
            {
                "wf-booking": {
                    "required_node_ids": ["trigger", "crm", "confirmation"],
                    "completion_node_id": "confirmation",
                }
            }
        ),
        "N8N_BASE_URL": "",
        "N8N_API_KEY": "",
        "N8N_DNS_NAMESERVERS": "[]",
        "INFRASTRUCTURE_MODE": "fixture",
        "INFRASTRUCTURE_DNS_NAMESERVERS": "[]",
        "INFRASTRUCTURE_TIMEOUT_SECONDS": "10",
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


def command(environment, module, *arguments):
    result = subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=ROOT / "backend",
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=45,
        creationflags=HIDDEN,
    )
    if result.returncode:
        raise RuntimeError(f"Frontend fixture CLI failed: {module}")
    return json.loads(result.stdout) if module != "app.db.cli" else None


def seed(client, environment):
    for check_id in ("supabase-health", "postgres"):
        client.post(f"/checks/infrastructure/{check_id}").raise_for_status()
    client.post("/checks/browser-flows/booking-healthy", timeout=45).raise_for_status()
    response = client.get("/n8n/executions/1001")
    response.raise_for_status()
    incident_id, check_id = response.headers["x-incident-id"], response.headers["x-check-id"]
    report = client.post(
        "/investigations", json={"question": "Why are booking confirmations missing?"}, timeout=45
    )
    report.raise_for_status()
    if report.json()["status"] != "COMPLETED":
        raise RuntimeError("Fixture investigation did not complete")
    action = command(
        environment,
        "app.actions.cli",
        "plan",
        "--incident-id",
        incident_id,
        "--check-id",
        check_id,
    )
    return {"incident_id": incident_id, "check_id": check_id, "action_id": action["id"]}


@contextmanager
def frontend_server(backend_url, *, port=0, name="frontend-smoke"):
    if not port:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required")
    logs = ROOT / "work" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        "RELIABILITY_BACKEND_URL": str(backend_url).rstrip("/"),
        "RELIABILITY_DASHBOARD_MODE": "local",
        "NEXT_TELEMETRY_DISABLED": "1",
    }
    with (logs / f"{name}.log").open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [
                node,
                str(ROOT / "frontend/node_modules/next/dist/bin/next"),
                "start",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT / "frontend",
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=HIDDEN,
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=20
            ) as client:
                deadline = time.monotonic() + 40
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Frontend exited; inspect its local log")
                    try:
                        response = client.get("/", timeout=1)
                        response.raise_for_status()
                        break
                    except httpx.TransportError:
                        if time.monotonic() > deadline:
                            raise RuntimeError("Frontend startup timed out") from None
                        time.sleep(0.1)
                yield client
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
