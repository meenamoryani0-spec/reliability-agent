"""Actual loopback HTTP and scratch storage; no live provider traffic."""

import json
import secrets

from frontend_support import command, fixture_environment
from smoke_support import ROOT, server


def main():
    environment = fixture_environment()
    token = secrets.token_urlsafe(32)
    environment.update(
        INVESTIGATION_MODE="disabled",
        N8N_MODE="disabled",
        N8N_RETRY_MODE="disabled",
        N8N_RECOVERY_MODE="disabled",
        INFRASTRUCTURE_MODE="disabled",
        N8N_EVENTS_ENABLED="true",
        N8N_EVENTS_TOKEN=token,
        N8N_EVENTS_WORKFLOW_IDS='["scratch-report"]',
        N8N_BASE_URL="https://n8n.example/api/v1/",
    )
    command(environment, "app.db.cli", "upgrade")
    with server(environment, ROOT / "work/logs/n8n-report-smoke.log") as backend:
        path = "/integrations/n8n/failures"
        body = {"workflow_id": "scratch-report", "execution_id": "123"}
        assert backend.post(path, json=body).status_code == 401
        headers = {"Authorization": "Bearer " + token}
        first = backend.post(path, headers=headers, json=body)
        first.raise_for_status()
        repeat = backend.post(path, headers=headers, json=body)
        repeat.raise_for_status()
        assert repeat.json()["check_id"] == first.json()["check_id"]
        assert backend.get("/history/incidents").json()[0]["observation_count"] == 1
        reports = backend.get("/monitoring/n8n/reports").json()
        assert len(reports["reports"]) == 1 and reports["absence_proves_health"] is False
        assert (
            backend.post(path, headers=headers, json={**body, "message": "private"}).status_code
            == 422
        )
    print(
        json.dumps(
            {
                "result": "PASS",
                "actual_http": True,
                "scratch_storage": True,
                "authenticated": True,
                "deduplicated": True,
                "live_provider_calls": False,
            }
        )
    )


if __name__ == "__main__":
    main()
