"""Actual CLI verification, HTTP proof reads and restart, with synthetic n8n only."""

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
        "STORAGE_SQLITE_FILE": f"work/data/recovery-smoke-{uuid4().hex}.sqlite3",
        "STORAGE_DATABASE_URL": "",
        "STORAGE_ALLOW_LOOPBACK": "false",
        "INCIDENTS_ENABLED": "true",
        "INVESTIGATION_MODE": "disabled",
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

    def command(module, *arguments):
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
        require(result.returncode == 0, f"Smoke CLI failed: {module}")
        return json.loads(result.stdout) if module != "app.db.cli" else None

    command("app.db.cli", "upgrade")
    logs = ROOT / "work" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with server(environment, logs / "recovery-before-restart.log") as client:
        response = client.get("/n8n/executions/1001")
        response.raise_for_status()
        require(
            response.headers["x-incident-status"] == "created",
            "Missing failed incident",
        )
        incident_id, check_id = (
            response.headers["x-incident-id"],
            response.headers["x-check-id"],
        )
        action = command(
            "app.actions.cli",
            "plan",
            "--incident-id",
            incident_id,
            "--check-id",
            check_id,
        )
        receipt = command(
            "app.actions.cli",
            "execute",
            "--action-id",
            action["id"],
            "--approve-retry-side-effects",
        )
        require(receipt["status"] == "ACCEPTED", "Missing accepted retry")
        require(
            client.get(f"/history/incidents/{incident_id}").json()["status"] == "OPEN",
            "Receipt resolved incident",
        )
        outcome = command("app.recovery.cli", "verify", "--action-id", action["id"])
        require(outcome["status"] == "VERIFIED", "Required path not verified")
        proof = outcome["verification"]
        require(
            proof["scope"] == "n8n_required_nodes" and not proof["business_outcome_verified"],
            "Workflow proof claimed customer outcome",
        )
        incident = client.get(f"/history/incidents/{incident_id}").json()
        require(incident["status"] == "RESOLVED", "Incident not resolved after proof")
        require(incident["resolution_verification_id"] == proof["id"], "Proof not bound")
        require(
            client.post("/recovery").status_code == 405,
            "Unexpected HTTP verification route",
        )
        saved = client.get("/history/verifications").json()
        require(len(saved) == 1, "Missing durable proof")
        require(
            client.get(f"/history/actions/{action['id']}").json()["recovery_verified"],
            "Action recovery read did not reflect proof",
        )
    with server(environment, logs / "recovery-after-restart.log") as client:
        require(
            client.get("/history/verifications").json() == saved,
            "Restart changed proof",
        )
        reused = command("app.recovery.cli", "verify", "--action-id", action["id"])
        require(
            reused["historical_proof_reused"],
            "Repeat verification performed a new read",
        )
        require(len(client.get("/history/verifications").json()) == 1, "Duplicate proof")
        response = client.get("/n8n/executions/1001")
        require(
            response.headers["x-incident-id"] == incident_id
            and response.headers["x-incident-status"] == "existing",
            "Historical failure reopened",
        )
        require(
            client.get(f"/history/incidents/{incident_id}").json()["status"] == "RESOLVED",
            "Historical repoll changed resolution",
        )
        require(
            "SYNTHETIC_PRIVATE_DATA" not in json.dumps(saved),
            "Private payload retained",
        )
    evidence = {
        "result": "PASS",
        "mode": "fixture",
        "real_cli_and_uvicorn": True,
        "accepted_receipt_did_not_resolve": True,
        "verification_status": "VERIFIED",
        "incident_status": "RESOLVED",
        "scope": "n8n_required_nodes",
        "historical_failure_repoll_did_not_reopen": True,
        "backend_restart_verified": True,
        "historical_proof_reused": True,
        "stored_verifications": 1,
        "business_outcome_verified": False,
        "live_provider_write_performed": False,
        "live_provider_read_performed": False,
        "storage": "scratch_local_sqlite_file",
    }
    path = ROOT / "work" / "evidence" / "phase-12-recovery-smoke.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
