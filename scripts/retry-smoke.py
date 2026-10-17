"""Actual operator CLI, HTTP audit reads and backend restart using synthetic n8n."""

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
        "STORAGE_SQLITE_FILE": f"work/data/retry-smoke-{uuid4().hex}.sqlite3",
        "STORAGE_DATABASE_URL": "",
        "STORAGE_ALLOW_LOOPBACK": "false",
        "INCIDENTS_ENABLED": "true",
        "INVESTIGATION_MODE": "disabled",
        "N8N_MODE": "fixture",
        "N8N_RETRY_MODE": "fixture",
        "N8N_RETRY_WORKFLOW_IDS": '["wf-booking"]',
        "N8N_BASE_URL": "",
        "N8N_API_KEY": "",
        "N8N_DNS_NAMESERVERS": "[]",
        "INFRASTRUCTURE_MODE": "disabled",
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
        timeout=20,
        creationflags=HIDDEN,
    )
    require(migration.returncode == 0, "Retry smoke migration failed")

    def cli(*arguments, expected_code=0):
        result = subprocess.run(
            [sys.executable, "-m", "app.actions.cli", *arguments],
            cwd=ROOT / "backend",
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=HIDDEN,
        )
        require(result.returncode == expected_code, "Unexpected operator CLI outcome")
        return json.loads(result.stdout)

    logs = ROOT / "work" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with server(environment, logs / "retry-before-restart.log") as client:
        response = client.get("/n8n/executions/1001")
        response.raise_for_status()
        require(response.headers["x-incident-status"] == "created", "Missing failed-check incident")
        incident_id, check_id = response.headers["x-incident-id"], response.headers["x-check-id"]
        plan = cli("plan", "--incident-id", incident_id, "--check-id", check_id)
        action_id = plan["id"]
        require(
            plan["state"] == "PENDING" and plan["approved_at"] is None, "Plan executed an action"
        )
        missing_approval = cli("execute", "--action-id", action_id, expected_code=1)
        require(missing_approval["reason"] == "explicit_approval_required", "Approval gate failed")
        require(
            client.get(f"/history/actions/{action_id}").json()["state"] == "PENDING",
            "Approval bypass",
        )
        result = cli("execute", "--action-id", action_id, "--approve-retry-side-effects")
        require(result["status"] == "ACCEPTED" and result["durable_outcome"], "Retry not accepted")
        require(result["action"]["new_execution_id"] == "2001", "Missing normalized receipt")
        require(
            result["action"]["provider_state"] == "running", "Fixture state changed unexpectedly"
        )
        require(not result["action"]["recovery_verified"], "Submission claimed recovery")
        repeat = cli(
            "execute", "--action-id", action_id, "--approve-retry-side-effects", expected_code=1
        )
        require(repeat["reason"] == "action_already_consumed", "Duplicate retry allowed")
        require(
            cli("plan", "--incident-id", incident_id, "--check-id", check_id)["id"] == action_id,
            "Repeated proposal created another action",
        )
        before = client.get("/history/actions").json()
        require(len(before) == 1 and before[0]["dispatch_started_at"], "Missing dispatch audit")
        require(
            client.get(f"/history/incidents/{incident_id}").json()["status"] == "OPEN",
            "Incident resolved",
        )
        require(client.post("/actions").status_code == 405, "Unexpected HTTP action write route")
        require(
            client.post(f"/actions/{action_id}/execute").status_code == 404,
            "HTTP execution route exists",
        )
        names = {item["function"]["name"] for item in client.get("/tools").json()["tools"]}
        require(len(names) == 13 and "retry_n8n_execution" not in names, "Model can execute retry")

    with server(environment, logs / "retry-after-restart.log") as client:
        require(
            client.get("/history/actions").json() == before, "Action audit changed across restart"
        )
        require(cli("inspect", "--action-id", action_id)["state"] == "ACCEPTED", "CLI lost action")
        repeat = cli(
            "execute", "--action-id", action_id, "--approve-retry-side-effects", expected_code=1
        )
        require(repeat["reason"] == "action_already_consumed", "Restart allowed duplicate retry")
        require(len(client.get("/history/actions").json()) == 1, "Duplicate action records")
        require(
            len(client.get("/history/checks").json()) == 1,
            "Receipt was treated as a recovery check",
        )
        require(
            client.get(f"/history/incidents/{incident_id}").json()["status"] == "OPEN",
            "Unverified resolution",
        )
        require(
            "SYNTHETIC_PRIVATE_DATA" not in json.dumps(before), "Private provider data in audit"
        )

    result = {
        "result": "PASS",
        "action": "retry_n8n_execution",
        "mode": "fixture",
        "accepted_actions": 1,
        "stored_action_records": 1,
        "missing_approval_blocked": True,
        "repeat_execution_blocked_before_and_after_restart": True,
        "backend_restart_verified": True,
        "new_execution_id": "2001",
        "provider_state": "running",
        "incident_status": "OPEN",
        "model_write_tools": 0,
        "http_execution_routes": 0,
        "recovery_verified": False,
        "live_provider_write_performed": False,
        "storage": "scratch_local_sqlite_file",
    }
    evidence = ROOT / "work" / "evidence" / "phase-11-retry-smoke.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
