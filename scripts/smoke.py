"""Start a real Uvicorn process, verify HTTP responses, and stop that process."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

project_root = Path(__file__).resolve().parents[1]
log_directory = project_root / "work" / "logs"
log_directory.mkdir(parents=True, exist_ok=True)

with socket.socket() as reserved_socket:
    reserved_socket.bind(("127.0.0.1", 0))
    port = reserved_socket.getsockname()[1]

server_environment = {
    **os.environ,
    "ENVIRONMENT": "test",
    "LOG_LEVEL": "INFO",
    "WEBSITE_TARGETS": "[]",
    "N8N_MODE": "fixture" if "--n8n" in sys.argv else "disabled",
    "N8N_BASE_URL": "",
    "N8N_API_KEY": "",
    "N8N_DNS_NAMESERVERS": "[]",
    "INFRASTRUCTURE_MODE": "fixture" if "--infrastructure" in sys.argv else "disabled",
    "INFRASTRUCTURE_DNS_NAMESERVERS": "[]",
    "INFRASTRUCTURE_TIMEOUT_SECONDS": "10",
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
    "STORAGE_MODE": "disabled",
    "STORAGE_SQLITE_FILE": "work/data/reliability.sqlite3",
    "STORAGE_DATABASE_URL": "",
    "STORAGE_ALLOW_LOOPBACK": "false",
}
with (log_directory / "smoke-server.log").open("w", encoding="utf-8") as server_log:
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=project_root / "backend",
        env=server_environment,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=1
        ) as client:
            deadline = time.monotonic() + 20
            while True:
                if server.poll() is not None:
                    raise RuntimeError(
                        "Server exited before health check; see work/logs/smoke-server.log"
                    )
                try:
                    health = client.get("/health")
                    break
                except httpx.TransportError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Live HTTP check timed out") from None
                    time.sleep(0.2)

            health.raise_for_status()
            expected = {"status": "ok", "service": "reliability-agent-backend"}
            if health.json() != expected:
                raise RuntimeError("Unexpected health response")
            schema = client.get("/openapi.json")
            schema.raise_for_status()
            if "/health" not in schema.json()["paths"]:
                raise RuntimeError("Health is missing from OpenAPI")
            docs = client.get("/docs")
            docs.raise_for_status()
            websites = client.get("/services/websites")
            websites.raise_for_status()
            if websites.json() != []:
                raise RuntimeError("Smoke test must start with no configured website targets")
            missing = client.post("/checks/websites/unconfigured")
            if missing.status_code != 404:
                raise RuntimeError("Unknown website target was not rejected")
            invalid = client.post("/checks/websites/unconfigured?kind=shell")
            if invalid.status_code != 422:
                raise RuntimeError("Unsupported check kind was not rejected")
            browser_results = []
            n8n_results = []
            infrastructure_results = []
            if "--infrastructure" in sys.argv:
                registry = client.get("/services/infrastructure")
                registry.raise_for_status()
                if registry.json()["mode"] != "fixture" or len(registry.json()["checks"]) != 5:
                    raise RuntimeError("Infrastructure fixture registry is not available")
                for check_id, expected_status in [
                    ("vercel-deployment", "UNHEALTHY"),
                    ("vercel-events", "UNKNOWN"),
                    ("supabase-project", "HEALTHY"),
                    ("supabase-health", "HEALTHY"),
                    ("postgres", "HEALTHY"),
                ]:
                    response = client.post(f"/checks/infrastructure/{check_id}", timeout=15)
                    response.raise_for_status()
                    result = response.json()
                    if (
                        result["status"] != expected_status
                        or result["inspection"] != "OK"
                        or result["synthetic"] is not True
                        or result["root_cause_verified"]
                        or result["business_outcome_verified"]
                    ):
                        raise RuntimeError("Infrastructure fixture returned unexpected evidence")
                    infrastructure_results.append(result)
                if client.post("/checks/infrastructure/arbitrary").status_code != 404:
                    raise RuntimeError("Unregistered infrastructure check was not rejected")
                if "SYNTHETIC_PRIVATE_DATA_DO_NOT_RETURN" in json.dumps(infrastructure_results):
                    raise RuntimeError("Private fixture data was retained")
                output_directory = project_root / "work" / "evidence"
                output_directory.mkdir(parents=True, exist_ok=True)
                (output_directory / "infrastructure-smoke.json").write_text(
                    json.dumps(infrastructure_results, indent=2), encoding="utf-8"
                )
            if "--n8n" in sys.argv:
                for path in [
                    "/n8n/workflows",
                    "/n8n/executions/failed?workflow_id=wf-booking",
                    "/n8n/executions/1001",
                    "/n8n/executions/1002",
                ]:
                    response = client.get(path, timeout=15)
                    response.raise_for_status()
                    result = response.json()
                    if result["status"] != "OK" or result["synthetic"] is not True:
                        raise RuntimeError("n8n fixture inspection did not complete")
                    n8n_results.append(result)
                failed = n8n_results[2]["execution"]
                healthy = n8n_results[3]["execution"]
                if failed["status"] != "UNHEALTHY" or healthy["status"] != "HEALTHY":
                    raise RuntimeError("n8n execution states did not match fixture evidence")
                if not any(
                    x["node_id"] == "crm" and x["http_status"] == 401 for x in failed["failures"]
                ):
                    raise RuntimeError("Missing recorded CRM authentication rejection")
                if any(x["node_id"] == "confirmation" for x in failed["observed_nodes"]):
                    raise RuntimeError("Failure fixture unexpectedly recorded confirmation")
                if not any(x["node_id"] == "confirmation" for x in healthy["observed_nodes"]):
                    raise RuntimeError("Success fixture is missing confirmation node execution")
                output_directory = project_root / "work" / "evidence"
                output_directory.mkdir(parents=True, exist_ok=True)
                (output_directory / "n8n-smoke.json").write_text(
                    json.dumps(n8n_results, indent=2), encoding="utf-8"
                )
            if "--browser" in sys.argv:
                flows = client.get("/services/browser-flows")
                flows.raise_for_status()
                if len(flows.json()) != 2:
                    raise RuntimeError("Expected two synthetic browser flows")
                for flow_id, status in [
                    ("booking-healthy", "HEALTHY"),
                    ("booking-crm-failure", "UNHEALTHY"),
                ]:
                    response = client.post(f"/checks/browser-flows/{flow_id}", timeout=45)
                    response.raise_for_status()
                    result = response.json()
                    if result["status"] != status:
                        raise RuntimeError("Browser flow did not produce expected evidence")
                    browser_results.append(result)
                output_directory = project_root / "work" / "evidence"
                output_directory.mkdir(parents=True, exist_ok=True)
                (output_directory / "browser-smoke.json").write_text(
                    json.dumps(browser_results, indent=2), encoding="utf-8"
                )
            print(
                json.dumps(
                    {
                        "result": "PASS",
                        "health_status": health.status_code,
                        "body": health.json(),
                        "docs_status": docs.status_code,
                        "website_list_status": websites.status_code,
                        "unconfigured_target_status": missing.status_code,
                        "invalid_check_kind_status": invalid.status_code,
                        "browser_flows": browser_results,
                        "n8n_reads": n8n_results,
                        "infrastructure_checks": infrastructure_results,
                    }
                )
            )
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
