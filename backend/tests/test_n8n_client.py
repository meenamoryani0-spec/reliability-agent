import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.tools.dns import ResolutionError
from app.tools.n8n import MAX_RESPONSE_BYTES, N8nClient, N8nService
from app.tools.n8n_fixtures import FIXTURE_BASE, execution_record
from app.tools.n8n_normalize import N8nError

KEY = "test-key-private"


def client_with(handler, *, addresses=None, timeout=10):
    async def resolver(host, _timeout):
        assert host == "n8n-fixture.test"
        return addresses if addresses is not None else ["93.184.216.34"]

    return N8nClient(
        FIXTURE_BASE,
        SecretStr(KEY),
        resolver=resolver,
        timeout=timeout,
        transport_factory=lambda: httpx.MockTransport(handler),
    )


def test_get_contract_auth_pinning_and_no_writes():
    seen = []

    def handler(request):
        assert request.method == "GET"
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "n8n-fixture.test"
        assert request.extensions["sni_hostname"] == "n8n-fixture.test"
        assert request.headers["X-N8N-API-KEY"] == KEY
        seen.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"data": [], "nextCursor": None})

    client = client_with(handler)

    async def run():
        await client.workflows(limit=2, cursor="opaque==")
        await client.failed_executions(workflow_id="wf-booking")
        await client.execution("1001")

    asyncio.run(run())
    assert seen == [
        ("/api/v1/workflows", {"limit": "2", "cursor": "opaque==", "excludePinnedData": "true"}),
        (
            "/api/v1/executions",
            {"limit": "25", "status": "error", "includeData": "false", "workflowId": "wf-booking"},
        ),
        ("/api/v1/executions/1001", {"includeData": "true"}),
    ]


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (401, "authentication_failed"),
        (403, "access_denied"),
        (404, "not_found"),
        (429, "rate_limited"),
        (500, "provider_error"),
        (302, "redirect_rejected"),
    ],
)
def test_provider_failure_is_sanitized_without_retry_or_redirect(status, reason):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=KEY, headers={"Location": "https://evil.example/"})

    result = asyncio.run(N8nService("live", client_with(handler)).read("workflows"))
    assert result.status == "CHECK_FAILED"
    assert result.reason == reason
    assert result.workflows == []
    assert KEY not in result.model_dump_json()
    assert len(calls) == 1


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["10.0.0.1"], ["93.184.216.34", "::1"]])
def test_all_dns_addresses_must_be_public_before_sending_key(addresses):
    called = False

    def handler(_request):
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    result = asyncio.run(
        N8nService("live", client_with(handler, addresses=addresses)).read("workflows")
    )
    assert result.reason == "non_public_destination"
    assert not called


def test_dns_failure_is_inspection_failure():
    async def resolver(_host, _timeout):
        raise ResolutionError("dns_nxdomain", confirmed=True)

    client = N8nClient(FIXTURE_BASE, SecretStr(KEY), resolver=resolver)
    result = asyncio.run(N8nService("live", client).read("workflows"))
    assert result.status == "CHECK_FAILED"
    assert result.reason == "dns_nxdomain"


@pytest.mark.parametrize(
    "body",
    ["bad JSON", "[]", "{}", '{"data":[]}', '{"data":[],"nextCursor":"https://evil.example"}'],
)
def test_invalid_pages_never_report_ok(body):
    client = client_with(
        lambda _: httpx.Response(200, content=body, headers={"content-type": "application/json"})
    )
    result = asyncio.run(N8nService("live", client).read("workflows"))
    assert result.status == "CHECK_FAILED"
    assert result.reason == "invalid_response"


def test_response_size_bound():
    client = client_with(
        lambda _: httpx.Response(
            200,
            content=b"x" * (MAX_RESPONSE_BYTES + 1),
            headers={"content-type": "application/json"},
        )
    )
    result = asyncio.run(N8nService("live", client).read("workflows"))
    assert result.reason == "response_too_large"


def test_html_login_page_is_not_valid_api_data():
    result = asyncio.run(
        N8nService(
            "live",
            client_with(
                lambda _: httpx.Response(200, text="login", headers={"content-type": "text/html"})
            ),
        ).read("workflows")
    )
    assert result.reason == "invalid_response"


def test_total_deadline():
    async def slow(_request):
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={})

    result = asyncio.run(N8nService("live", client_with(slow, timeout=0.01)).read("workflows"))
    assert result.reason == "timeout"


def test_transport_exception_does_not_retain_details():
    def handler(_request):
        raise httpx.ConnectError(KEY)

    result = asyncio.run(N8nService("live", client_with(handler)).read("workflows"))
    assert result.reason == "transport_error"
    assert KEY not in result.model_dump_json()


def test_execution_identity_is_verified():
    client = client_with(lambda _: httpx.Response(200, json=execution_record("1002", failed=False)))
    result = asyncio.run(N8nService("live", client).read("execution", execution_id="1001"))
    assert result.reason == "execution_identity_mismatch"
    assert result.execution is None


@pytest.mark.parametrize(
    ("record", "workflow_id", "reason"),
    [
        (execution_record("1002", failed=False), None, "unexpected_execution_state"),
        (execution_record("1001", failed=True), "different", "workflow_identity_mismatch"),
    ],
)
def test_failed_execution_filter_is_verified(record, workflow_id, reason):
    client = client_with(lambda _: httpx.Response(200, json={"data": [record], "nextCursor": None}))
    result = asyncio.run(
        N8nService("live", client).read("failed_executions", workflow_id=workflow_id)
    )
    assert result.reason == reason
    assert not result.executions


def test_page_limits_and_opaque_cursor_are_preserved_without_automatic_paging():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"data": [{"id": "wf", "active": False}], "nextCursor": "another-page=="}
        )

    result = asyncio.run(N8nService("live", client_with(handler)).read("workflows", limit=1))
    assert result.status == "OK"
    assert result.next_cursor == "another-page=="
    assert len(calls) == 1


def test_provider_cannot_exceed_requested_limit_or_echo_key_in_metadata():
    for payload, limit in [
        (
            {
                "data": [{"id": "wf1", "active": True}, {"id": "wf2", "active": True}],
                "nextCursor": None,
            },
            1,
        ),
        ({"data": [{"id": KEY, "active": True}], "nextCursor": None}, 25),
    ]:
        client = client_with(
            lambda _, payload=payload: httpx.Response(
                200, content=json.dumps(payload), headers={"content-type": "application/json"}
            )
        )
        result = asyncio.run(N8nService("live", client).read("workflows", limit=limit))
        assert result.reason == "invalid_response"
        assert KEY not in result.model_dump_json()


@pytest.mark.parametrize(
    "value", ["../credentials", "0", "1001?x=1", "https://evil.example", "1/2"]
)
def test_invalid_execution_id_never_dispatches(value):
    def handler(_request):
        pytest.fail("Must not send invalid paths")

    with pytest.raises(N8nError):
        asyncio.run(client_with(handler).execution(value))


def test_private_or_write_paths_rejected():
    client = client_with(lambda _: pytest.fail("Must not dispatch"))
    for path in [
        "credentials",
        "executions/1001/retry",
        "workflows/wf/activate",
        "https://evil.example",
    ]:
        with pytest.raises(N8nError, match="invalid_request"):
            asyncio.run(client._get(path, {}))
