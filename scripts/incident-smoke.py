"""Verify opt-in incident creation over HTTP, including a real server restart."""

import json
import os
import subprocess
import sys
from uuid import uuid4

from smoke_support import HIDDEN, ROOT, server


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    environment = {
        **os.environ,
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "INFO",
        "STORAGE_MODE": "local",
        "STORAGE_SQLITE_FILE": f"work/data/incident-smoke-{uuid4().hex}.sqlite3",
        "STORAGE_DATABASE_URL": "",
        "STORAGE_ALLOW_LOOPBACK": "false",
        "INCIDENTS_ENABLED": "true",
        "INVESTIGATION_MODE": "fixture",
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
    require(migration.returncode == 0, "Incident smoke migration failed")
    logs = ROOT / "work" / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    def investigation(client):
        response = client.post(
            "/investigations",
            json={"question": "Why are booking confirmations missing?"},
            timeout=45,
        )
        response.raise_for_status()
        report = response.json()
        require(report["status"] == "COMPLETED", "Investigation did not complete")
        require(report["inference_source"] == "scripted_fixture", "Unexpected inference mode")
        require(len(report["incident_ids"]) == 1, "Missing evidence-linked incident")
        require(report["incident_assessment"]["status"] == "saved", "Assessment was not saved")
        require(len(report["incident_assessment"]["check_ids"]) == 1, "Wrong assessment evidence")
        require(
            not report["root_cause_verified"] and not report["remediation_executed"],
            "Unverified cause or action reported",
        )
        return report

    def check(client, method, path, expected):
        response = client.request(method, path, timeout=45)
        response.raise_for_status()
        require(response.headers.get("x-history-status") == "saved", "Check was not saved")
        require(response.headers.get("x-incident-status") == expected, "Unexpected detection state")
        return response

    with server(environment, logs / "incident-before-restart.log") as client:
        first, second = investigation(client), investigation(client)
        require(first["incident_created"] and not second["incident_created"], "Duplicate incident")
        require(first["incident_ids"] == second["incident_ids"], "Incident identity changed")
        repeated = check(client, "GET", "/n8n/executions/1001", "existing")
        require(repeated.headers["x-incident-id"] == first["incident_ids"][0], "Wrong incident")
        check(client, "GET", "/n8n/executions/1002", "not_applicable")
        check(client, "GET", "/n8n/executions/9999", "not_applicable")
        check(client, "POST", "/checks/infrastructure/vercel-deployment", "created")
        check(client, "POST", "/checks/browser-flows/booking-crm-failure", "created")
        before = client.get("/history/incidents?limit=100").json()
        checks_before = client.get("/history/checks?limit=100").json()
        incident_id = first["incident_ids"][0]
        assessments_before = client.get(f"/history/incidents/{incident_id}/assessments").json()
        require(len(assessments_before) == 2, "Missing supported assessments")
        require(len(before) == 3 and len(checks_before) == 11, "Unexpected persisted totals")
        require(all(row["status"] == "OPEN" and row["synthetic"] for row in before), "Wrong state")
        require(client.get("/history/incidents?synthetic=false").json() == [], "Fixture mislabeled")
        require(client.post("/history/incidents").status_code == 405, "Public incident write route")

    with server(environment, logs / "incident-after-restart.log") as client:
        require(client.get("/history/incidents?limit=100").json() == before, "Incidents changed")
        require(client.get("/history/checks?limit=100").json() == checks_before, "Checks changed")
        require(
            client.get(f"/history/incidents/{incident_id}/assessments").json()
            == assessments_before,
            "Assessments did not survive restart",
        )
        third = investigation(client)
        require(not third["incident_created"], "Restart duplicated an incident")
        require(third["incident_ids"] == first["incident_ids"], "Restart lost incident identity")
        check(client, "POST", "/checks/infrastructure/vercel-deployment", "existing")
        incidents = client.get("/history/incidents?limit=100").json()
        checks = client.get("/history/checks?limit=100").json()
        assessments = client.get(f"/history/incidents/{incident_id}/assessments").json()
        require(len(assessments) == 3, "Unexpected assessment total")
        require(
            all(
                row["root_cause"] is None
                and not row["root_cause_verified"]
                and row["hypothesis"] == "authentication_rejection"
                and row["inference_source"] == "scripted_fixture"
                and row["recommended_steps"] == third["next_steps"]
                for row in assessments
            ),
            "Unverified diagnosis or recommendations",
        )
        for row in incidents:
            identifier = row["id"]
            detail = client.get(f"/history/incidents/{identifier}").json()
            observations = client.get(
                f"/history/incidents/{identifier}/observations?limit=100"
            ).json()
            require(detail == row, "Detail/list disagree")
            require(len(observations) == row["observation_count"], "Evidence count differs")
            require(all(item["status"] == "UNHEALTHY" for item in observations), "Invalid evidence")
            require(not row["root_cause_verified"] and not row["verified"], "Unverified fact")
        serialized = json.dumps({"incidents": incidents, "checks": checks})
        require("SYNTHETIC_PRIVATE_DATA_DO_NOT_RETURN" not in serialized, "Private data persisted")
        require(len(incidents) == 3 and len(checks) == 15, "Unexpected post-restart totals")

    result = {
        "result": "PASS",
        "checks_persisted": len(checks),
        "incidents": len(incidents),
        "supported_assessments_persisted": len(assessments),
        "linked_unhealthy_observations": sum(row["observation_count"] for row in incidents),
        "observation_counts": {row["component"]: row["observation_count"] for row in incidents},
        "backend_restart_verified": True,
        "duplicate_incidents": 0,
        "healthy_check_did_not_resolve": True,
        "inference_mode": "scripted_fixture",
        "monitoring_data": "synthetic_fixtures_with_real_chromium",
        "live_providers_verified": False,
        "storage": "scratch_local_sqlite_file",
    }
    evidence = ROOT / "work" / "evidence" / "phase-10-incidents-smoke.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
