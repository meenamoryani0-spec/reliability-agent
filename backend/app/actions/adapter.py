"""One bounded n8n retry POST, using the original saved workflow only."""

import json
from typing import Literal

import httpx
from pydantic import TypeAdapter

from app.tools.n8n import N8nClient
from app.tools.n8n_fixtures import FIXTURE_BASE, FIXTURE_KEY, fixture_response
from app.tools.n8n_models import ExecutionId, ExecutionState, ResourceId
from app.tools.n8n_normalize import N8nError, ProviderMetadata, execution_evidence, normalize_errors


class Eligibility(ProviderMetadata):
    id: ExecutionId
    workflowId: ResourceId
    status: Literal["error"]
    retryOf: None
    retrySuccessId: None


class Receipt(ProviderMetadata):
    id: ExecutionId
    workflowId: ResourceId
    mode: Literal["retry"]
    retryOf: ExecutionId
    status: ExecutionState


class N8nRetryClient(N8nClient):
    async def preflight(self, execution_id, workflow_id):
        raw = await self.execution(execution_id)
        item = normalize_errors(lambda: Eligibility.model_validate(raw))
        evidence = normalize_errors(lambda: execution_evidence(raw))
        if (
            item.id != execution_id
            or item.workflowId != workflow_id
            or evidence.status != "UNHEALTHY"
            or evidence.data_availability != "present"
        ):
            raise N8nError("execution_not_eligible")
        return None

    async def retry_n8n_execution(self, execution_id, workflow_id):
        identifier = normalize_errors(
            lambda: TypeAdapter(ExecutionId).validate_python(execution_id)
        )
        workflow = normalize_errors(lambda: TypeAdapter(ResourceId).validate_python(workflow_id))
        raw = await self._request("POST", f"executions/{identifier}/retry", {})
        receipt = normalize_errors(lambda: Receipt.model_validate(raw))
        if (
            receipt.id == identifier
            or receipt.retryOf != identifier
            or receipt.workflowId != workflow
            or self._key.get_secret_value() in receipt.model_dump_json()
        ):
            raise N8nError("retry_identity_mismatch")
        return receipt


def retry_client(config):
    if config.n8n_retry_mode == "fixture":
        from pydantic import SecretStr

        async def resolver(_host, _timeout):
            return ["93.184.216.34"]

        def handler(request):
            if request.method == "GET":
                return fixture_response(request)
            if (
                request.method == "POST"
                and request.url.path == "/api/v1/executions/1001/retry"
                and request.headers.get("X-N8N-API-KEY") == FIXTURE_KEY
                and json.loads(request.content) == {"loadWorkflow": False}
            ):
                return httpx.Response(
                    200,
                    json={
                        "id": "2001",
                        "workflowId": "wf-booking",
                        "mode": "retry",
                        "retryOf": "1001",
                        "status": "running",
                        "data": {"private": "SYNTHETIC_PRIVATE_DATA"},
                    },
                )
            return httpx.Response(405)

        return N8nRetryClient(
            FIXTURE_BASE,
            SecretStr(FIXTURE_KEY),
            resolver=resolver,
            transport_factory=lambda: httpx.MockTransport(handler),
        )
    if config.n8n_retry_mode == "live":
        return N8nRetryClient(
            config.n8n_base_url,
            config.n8n_api_key,
            timeout=config.n8n_timeout_seconds,
            nameservers=config.n8n_dns_nameservers,
        )
    return None
