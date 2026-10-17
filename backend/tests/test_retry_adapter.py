import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.actions.adapter import N8nRetryClient
from app.tools.n8n import MAX_RESPONSE_BYTES
from app.tools.n8n_fixtures import FIXTURE_BASE, execution_record
from app.tools.n8n_normalize import N8nError

KEY = "PRIVATE_RETRY_KEY"


def adapter(handler, *, addresses=None, timeout=1):
    async def resolver(_host, _timeout):
        return addresses if addresses is not None else ["93.184.216.34"]

    return N8nRetryClient(
        FIXTURE_BASE,
        SecretStr(KEY),
        resolver=resolver,
        timeout=timeout,
        transport_factory=lambda: httpx.MockTransport(handler),
    )


def receipt(**options):
    return {
        "id": "2001",
        "workflowId": "wf-booking",
        "mode": "retry",
        "retryOf": "1001",
        "status": "running",
        **options,
    }


def test_exact_retry_contract_original_workflow_auth_pinning_and_sanitized_receipt():
    seen = []

    def handler(request):
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "n8n-fixture.test"
        assert request.extensions["sni_hostname"] == "n8n-fixture.test"
        assert request.headers["X-N8N-API-KEY"] == KEY
        seen.append((request.method, request.url.path))
        if request.method == "GET":
            assert dict(request.url.params) == {"includeData": "true"}
            return httpx.Response(200, json=execution_record("1001", failed=True))
        assert not request.url.params and json.loads(request.content) == {"loadWorkflow": False}
        return httpx.Response(
            200, json=receipt(data={"private": KEY}, workflowData={"private": KEY})
        )

    client = adapter(handler)

    async def run():
        await client.preflight("1001", "wf-booking")
        return await client.retry_n8n_execution("1001", "wf-booking")

    value = asyncio.run(run())
    assert value.id == "2001" and value.status == "running"
    assert KEY not in value.model_dump_json() and "workflowData" not in value.model_dump_json()
    assert seen == [("GET", "/api/v1/executions/1001"), ("POST", "/api/v1/executions/1001/retry")]


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "success"},
        {"status": "running"},
        {"status": "waiting"},
        {"retryOf": "999"},
        {"retrySuccessId": "2000"},
        {"id": "222"},
        {"workflowId": "other"},
        {"data": {}},
        {"dataTooLargeToDisplay": True},
    ],
)
def test_preflight_rejects_ineligible_or_changed_execution_without_any_post(changes):
    seen = []

    def handler(request):
        seen.append(request.method)
        return httpx.Response(200, json={**execution_record("1001", failed=True), **changes})

    with pytest.raises(N8nError):
        asyncio.run(adapter(handler).preflight("1001", "wf-booking"))
    assert seen == ["GET"]


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "1001"},
        {"id": "../evil"},
        {"workflowId": "other"},
        {"workflowId": KEY},
        {"retryOf": "999"},
        {"mode": "manual"},
        {"status": "made_up"},
    ],
)
def test_invalid_post_receipts_fail_without_automatic_resubmission(changes):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=receipt(**changes))

    with pytest.raises(N8nError):
        asyncio.run(adapter(handler).retry_n8n_execution("1001", "wf-booking"))
    assert len(seen) == 1


@pytest.mark.parametrize("status", [301, 307, 400, 401, 403, 404, 409, 429, 500])
def test_post_failure_never_redirects_retries_or_exposes_response_body(status):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, text=KEY, headers={"location": "https://evil.example"})

    with pytest.raises(N8nError) as error:
        asyncio.run(adapter(handler).retry_n8n_execution("1001", "wf-booking"))
    assert len(seen) == 1 and KEY not in str(error.value)


@pytest.mark.parametrize("identifier", ["../1", "0", "1?x=y", "1/retry", 1, True])
def test_invalid_execution_ids_cannot_start_requests(identifier):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=receipt())

    with pytest.raises(N8nError):
        asyncio.run(adapter(handler).retry_n8n_execution(identifier, "wf-booking"))
    assert seen == []


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["10.0.0.1"], ["169.254.169.254"]])
def test_retry_does_not_reach_nonpublic_destinations(addresses):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=receipt())

    with pytest.raises(N8nError):
        asyncio.run(adapter(handler, addresses=addresses).retry_n8n_execution("1001", "wf-booking"))
    assert seen == []


@pytest.mark.parametrize("kind", ["timeout", "malformed", "oversized", "wrong_content_type"])
def test_uncertain_or_unparseable_post_response_is_not_retried(kind):
    seen = []

    async def handler(request):
        seen.append(request)
        if kind == "timeout":
            await asyncio.sleep(1)
        if kind == "oversized":
            return httpx.Response(
                200,
                content=b"x" * (MAX_RESPONSE_BYTES + 1),
                headers={"content-type": "application/json"},
            )
        if kind == "malformed":
            return httpx.Response(
                200,
                content=b'{"id":"2001","id":"2002"}',
                headers={"content-type": "application/json"},
            )
        return httpx.Response(200, text=KEY)

    with pytest.raises(N8nError):
        asyncio.run(adapter(handler, timeout=0.05).retry_n8n_execution("1001", "wf-booking"))
    assert len(seen) == 1
