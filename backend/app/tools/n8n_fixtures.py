"""Synthetic provider-shaped records, served only by an in-memory GET transport."""

from copy import deepcopy

import httpx
from pydantic import SecretStr

from app.tools.n8n import N8nClient

FIXTURE_BASE = "https://n8n-fixture.test/api/v1/"
FIXTURE_KEY = "synthetic-n8n-key-not-a-credential"
PRIVATE_CANARY = "SYNTHETIC_PRIVATE_DATA"
NODES = [
    {"id": "trigger", "name": "Booking request", "type": "n8n-nodes-base.webhook"},
    {
        "id": "crm",
        "name": "CRM",
        "type": "n8n-nodes-base.httpRequest",
        "parameters": {"url": "https://crm.example/private", "headers": {"token": PRIVATE_CANARY}},
        "credentials": {"httpHeaderAuth": {"id": "synthetic", "name": PRIVATE_CANARY}},
    },
    {"id": "confirmation", "name": "Send confirmation", "type": "n8n-nodes-base.httpRequest"},
]
ERROR = {
    "name": "NodeApiError",
    "httpCode": "401",
    "node": NODES[1],
    "message": PRIVATE_CANARY,
    "stack": PRIVATE_CANARY,
    "description": PRIVATE_CANARY,
}


def execution_record(execution_id: str, *, failed: bool) -> dict:
    runs = {
        "Booking request": [
            {
                "executionStatus": "success",
                "executionTime": 1,
                "data": {"main": [[{"json": {"customer": PRIVATE_CANARY}}]]},
            }
        ]
    }
    runs["CRM"] = [
        {
            "executionStatus": "error" if failed else "success",
            "executionTime": 5,
            **({"error": ERROR} if failed else {}),
        }
    ]
    if not failed:
        runs["Send confirmation"] = [{"executionStatus": "success", "executionTime": 2}]
    return {
        "id": execution_id,
        "workflowId": "wf-booking",
        "status": "error" if failed else "success",
        "finished": not failed,
        "mode": "webhook",
        "retryOf": None,
        "retrySuccessId": None,
        "startedAt": "2026-10-11T00:00:00Z",
        "stoppedAt": "2026-10-11T00:00:01Z",
        "waitTill": None,
        "workflowData": {"id": "wf-booking", "name": PRIVATE_CANARY, "nodes": NODES},
        "data": {
            "version": 1,
            "resultData": {
                "runData": runs,
                "lastNodeExecuted": "CRM" if failed else "Send confirmation",
                **({"error": ERROR} if failed else {}),
            },
        },
    }


def fixture_response(request: httpx.Request) -> httpx.Response:
    if request.method != "GET":
        return httpx.Response(405)
    if request.headers.get("X-N8N-API-KEY") != FIXTURE_KEY:
        return httpx.Response(401)
    if request.url.path == "/api/v1/workflows":
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "wf-booking", "active": True, "name": PRIVATE_CANARY, "nodes": NODES}
                ],
                "nextCursor": None,
            },
        )
    if request.url.path == "/api/v1/executions":
        records = [execution_record("1001", failed=True)]
        workflow_id = request.url.params.get("workflowId")
        if workflow_id is not None and workflow_id != "wf-booking":
            records = []
        return httpx.Response(200, json={"data": records, "nextCursor": None})
    if request.url.path in {"/api/v1/executions/1001", "/api/v1/executions/1002"}:
        identifier = request.url.path.rsplit("/", 1)[1]
        return httpx.Response(
            200, json=deepcopy(execution_record(identifier, failed=identifier == "1001"))
        )
    return httpx.Response(404)


def fixture_client() -> N8nClient:
    async def resolver(_host, _timeout):
        # The address passes the same policy; MockTransport never opens a network socket.
        return ["93.184.216.34"]

    return N8nClient(
        FIXTURE_BASE,
        SecretStr(FIXTURE_KEY),
        resolver=resolver,
        transport_factory=lambda: httpx.MockTransport(fixture_response),
    )
