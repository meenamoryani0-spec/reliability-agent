import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.tools.infrastructure import InfrastructureService
from app.tools.infrastructure_fixtures import DEPLOYMENT_ID, PRIVATE_MARKER, PROJECT_REF
from app.tools.infrastructure_http import MAX_RESPONSE_BYTES, InfrastructureHttp
from app.tools.infrastructure_models import CHECK_IDS, InfrastructureError

TOKEN = "PRIVATE_TEST_TOKEN"


def config(**kwargs):
    return Settings(_env_file=None, **kwargs)


def make_client(handler, provider="vercel", *, addresses=None, timeout=10):
    async def resolver(host, _timeout):
        assert host == {"vercel": "api.vercel.com", "supabase": "api.supabase.com"}[provider]
        return ["93.184.216.34"] if addresses is None else addresses

    return InfrastructureHttp(
        provider,
        SecretStr(TOKEN),
        resolver=resolver,
        timeout=timeout,
        transport_factory=lambda: httpx.MockTransport(handler),
    )


def service_for(raw, provider="vercel", **kwargs):
    client = make_client(
        lambda _: httpx.Response(
            200, content=json.dumps(raw).encode(), headers={"content-type": "application/json"}
        ),
        provider,
    )
    return InfrastructureService(
        config(
            infrastructure_mode="live",
            vercel_deployment_id=DEPLOYMENT_ID,
            supabase_project_ref=PROJECT_REF,
            **kwargs,
        ),
        **{provider: client},
    )


def test_fixture_checks_have_distinct_scopes_and_no_private_payloads():
    service = InfrastructureService(config(infrastructure_mode="fixture"))

    async def run():
        return [await service.check(check) for check in CHECK_IDS]

    results = asyncio.run(run())
    assert [row.status for row in results] == [
        "UNHEALTHY",
        "UNKNOWN",
        "HEALTHY",
        "HEALTHY",
        "HEALTHY",
    ]
    for row in results:
        assert row.inspection == "OK" and row.synthetic
        assert not row.root_cause_verified and not row.business_outcome_verified
        assert PRIVATE_MARKER not in row.model_dump_json()
    assert results[1].healthy is None
    assert results[0].evidence["production_alias_verified"] is False


@pytest.mark.parametrize("check", CHECK_IDS)
@pytest.mark.parametrize(
    "mode,reason", [("disabled", "integration_disabled"), ("live", "missing_configuration")]
)
def test_missing_provider_access_is_not_unhealthy(check, mode, reason):
    result = asyncio.run(InfrastructureService(config(infrastructure_mode=mode)).check(check))
    assert result.status == "CHECK_FAILED" and result.healthy is None
    assert result.inspection == "CHECK_FAILED" and result.reason == reason


def test_documented_get_contract_auth_and_pinning():
    seen = []

    def handler(request):
        assert request.method == "GET"
        assert request.url.host == "93.184.216.34"
        host = request.headers["host"]
        assert host in {"api.vercel.com", "api.supabase.com"}
        assert request.extensions["sni_hostname"] == host
        assert request.headers["authorization"] == "Bearer " + TOKEN
        seen.append((host, request.url.path, dict(request.url.params)))
        if request.url.path.endswith("/events"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/health"):
            return httpx.Response(
                200,
                json=[
                    {"name": name, "status": "ACTIVE_HEALTHY", "healthy": True}
                    for name in ("db", "auth", "rest")
                ],
            )
        if host == "api.vercel.com":
            return httpx.Response(200, json={"id": DEPLOYMENT_ID, "readyState": "READY"})
        return httpx.Response(200, json={"ref": PROJECT_REF, "status": "ACTIVE_HEALTHY"})

    service = InfrastructureService(
        config(
            infrastructure_mode="live",
            vercel_deployment_id=DEPLOYMENT_ID,
            vercel_team_id="team_test",
            supabase_project_ref=PROJECT_REF,
        ),
        vercel=make_client(handler),
        supabase=make_client(handler, "supabase"),
    )

    async def run():
        for check in CHECK_IDS[:-1]:
            assert (await service.check(check)).inspection == "OK"

    asyncio.run(run())
    assert seen == [
        ("api.vercel.com", f"/v13/deployments/{DEPLOYMENT_ID}", {"teamId": "team_test"}),
        (
            "api.vercel.com",
            f"/v3/deployments/{DEPLOYMENT_ID}/events",
            {
                "teamId": "team_test",
                "direction": "backward",
                "follow": "0",
                "limit": "25",
                "builds": "1",
            },
        ),
        ("api.supabase.com", f"/v1/projects/{PROJECT_REF}", {}),
        (
            "api.supabase.com",
            f"/v1/projects/{PROJECT_REF}/health",
            {"services": "db,auth,rest", "timeout_ms": "2000"},
        ),
    ]


@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "authentication_failed"),
        (403, "access_denied"),
        (404, "not_found"),
        (429, "rate_limited"),
        (500, "provider_error"),
        (302, "redirect_rejected"),
    ],
)
def test_http_failures_are_sanitized_without_retries(status, reason):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=TOKEN, headers={"Location": "http://127.0.0.1/"})

    service = InfrastructureService(
        config(infrastructure_mode="live", vercel_deployment_id=DEPLOYMENT_ID),
        vercel=make_client(handler),
    )
    result = asyncio.run(service.check("vercel-deployment"))
    assert result.reason == reason and result.healthy is None
    assert TOKEN not in result.model_dump_json() and len(calls) == 1


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["10.0.0.1"], ["93.184.216.34", "::1"], []])
def test_unsafe_dns_is_rejected_before_credentials_sent(addresses):
    def handler(_request):
        pytest.fail("Unsafe destination was contacted")

    service = InfrastructureService(
        config(infrastructure_mode="live", vercel_deployment_id=DEPLOYMENT_ID),
        vercel=make_client(handler, addresses=addresses),
    )
    result = asyncio.run(service.check("vercel-deployment"))
    assert result.inspection == "CHECK_FAILED" and result.healthy is None


@pytest.mark.parametrize(
    "body",
    [
        b"bad json",
        b"[]",
        b"null",
        b"{}",
        b'{"id":1,"id":2}',
        b'{"id":NaN}',
        pytest.param(b"x" * (MAX_RESPONSE_BYTES + 1), id="oversized"),
    ],
)
def test_invalid_and_oversized_responses_are_not_healthy(body):
    service = InfrastructureService(
        config(infrastructure_mode="live", vercel_deployment_id=DEPLOYMENT_ID),
        vercel=make_client(
            lambda _: httpx.Response(
                200, content=body, headers={"content-type": "application/json"}
            )
        ),
    )
    result = asyncio.run(service.check("vercel-deployment"))
    assert result.inspection == "CHECK_FAILED" and result.healthy is None


def test_html_response_is_not_a_deployment():
    service = InfrastructureService(
        config(infrastructure_mode="live", vercel_deployment_id=DEPLOYMENT_ID),
        vercel=make_client(lambda _: httpx.Response(200, text=TOKEN)),
    )
    assert asyncio.run(service.check("vercel-deployment")).reason == "invalid_response"


def test_http_deadline_and_transport_failure():
    async def slow(_request):
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={})

    async def disconnected(_request):
        raise httpx.ConnectError(TOKEN)

    for handler, reason in [(slow, "timeout"), (disconnected, "transport_error")]:
        service = InfrastructureService(
            config(infrastructure_mode="live", vercel_deployment_id=DEPLOYMENT_ID),
            vercel=make_client(handler, timeout=0.01),
        )
        result = asyncio.run(service.check("vercel-deployment"))
        assert result.reason == reason and TOKEN not in result.model_dump_json()


@pytest.mark.parametrize(
    "state,expected",
    [
        ("READY", "HEALTHY"),
        ("ERROR", "UNHEALTHY"),
        ("BLOCKED", "UNHEALTHY"),
        ("CANCELED", "UNKNOWN"),
        ("BUILDING", "UNKNOWN"),
        ("QUEUED", "UNKNOWN"),
        ("INITIALIZING", "UNKNOWN"),
    ],
)
def test_deployment_state_is_scoped_not_a_runtime_diagnosis(state, expected):
    result = asyncio.run(
        service_for(
            {"id": DEPLOYMENT_ID, "readyState": state, "errorMessage": PRIVATE_MARKER}
        ).check("vercel-deployment")
    )
    assert result.status == expected
    assert not result.evidence["production_alias_verified"]
    assert PRIVATE_MARKER not in result.model_dump_json()


@pytest.mark.parametrize(
    "provider,check,raw,reason",
    [
        (
            "vercel",
            "vercel-deployment",
            {"id": "dpl_other", "readyState": "READY"},
            "deployment_identity_mismatch",
        ),
        (
            "supabase",
            "supabase-project",
            {"ref": "z" * 20, "status": "ACTIVE_HEALTHY"},
            "project_identity_mismatch",
        ),
    ],
)
def test_provider_resource_identity_is_checked(provider, check, raw, reason):
    assert asyncio.run(service_for(raw, provider).check(check)).reason == reason


@pytest.mark.parametrize(
    "state,expected",
    [
        ("ACTIVE_HEALTHY", "HEALTHY"),
        ("ACTIVE_UNHEALTHY", "UNHEALTHY"),
        ("INACTIVE", "UNKNOWN"),
        ("REMOVED", "UNKNOWN"),
        ("RESTORING", "UNKNOWN"),
        ("INIT_FAILED", "UNHEALTHY"),
    ],
)
def test_supabase_project_state(state, expected):
    result = asyncio.run(
        service_for({"ref": PROJECT_REF, "status": state}, "supabase").check("supabase-project")
    )
    assert result.status == expected


@pytest.mark.parametrize(
    "state,expected",
    [("ACTIVE_HEALTHY", "HEALTHY"), ("UNHEALTHY", "UNHEALTHY"), ("COMING_UP", "DEGRADED")],
)
def test_supabase_service_health(state, expected):
    raw = [
        {
            "name": name,
            "status": state,
            "healthy": state == "ACTIVE_HEALTHY",
            "error": PRIVATE_MARKER,
        }
        for name in ("db", "auth", "rest")
    ]
    result = asyncio.run(service_for(raw, "supabase").check("supabase-health"))
    assert result.status == expected and PRIVATE_MARKER not in result.model_dump_json()


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {},
        None,
        [{"name": "db", "status": "ACTIVE_HEALTHY", "healthy": True}] * 3,
        [
            {"name": name, "status": "ACTIVE_HEALTHY", "healthy": False}
            for name in ("db", "auth", "rest")
        ],
        [
            {"name": name, "status": "ACTIVE_HEALTHY", "healthy": "true"}
            for name in ("db", "auth", "rest")
        ],
    ],
)
def test_missing_duplicate_or_contradictory_health_cannot_report_healthy(raw):
    result = asyncio.run(service_for(raw, "supabase").check("supabase-health"))
    assert result.inspection == "CHECK_FAILED" and result.healthy is None


@pytest.mark.parametrize("wrapped", [True, False])
def test_events_keep_only_safe_metadata_and_do_not_infer_health(wrapped):
    payload = {
        "deploymentId": DEPLOYMENT_ID,
        "text": PRIVATE_MARKER,
        "info": {"path": PRIVATE_MARKER},
    }
    row = {"created": 123, "type": "stderr", **({"payload": payload} if wrapped else payload)}
    result = asyncio.run(service_for([row]).check("vercel-events"))
    assert result.status == "UNKNOWN" and result.healthy is None
    assert result.evidence["events"] == [{"type": "stderr", "created_ms": 123}]
    assert PRIVATE_MARKER not in result.model_dump_json()


@pytest.mark.parametrize("raw", [[], None])
def test_no_events_is_not_proof_of_health(raw):
    result = asyncio.run(service_for(raw).check("vercel-events"))
    assert result.status == "UNKNOWN" and result.inspection == "OK"


@pytest.mark.parametrize(
    "raw",
    [
        [{"created": 123, "type": "stdout", "deploymentId": "dpl_other"}],
        [{"created": True, "type": "stdout", "deploymentId": DEPLOYMENT_ID}],
        [{"created": 123, "type": "stdout", "payload": None}],
        [{"created": 123, "type": "stdout", "deploymentId": DEPLOYMENT_ID}] * 26,
    ],
)
def test_unsafe_or_unbounded_event_evidence_fails(raw):
    result = asyncio.run(service_for(raw).check("vercel-events"))
    assert result.healthy is None and result.inspection == "CHECK_FAILED"


def test_secret_echo_in_retained_id_is_blocked():
    result = asyncio.run(
        service_for({"id": DEPLOYMENT_ID, "readyState": "READY"}, vercel_token=DEPLOYMENT_ID).check(
            "vercel-deployment"
        )
    )
    assert result.reason == "invalid_response" and DEPLOYMENT_ID not in json.dumps(result.evidence)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"postgres_host": "localhost"},
        {"postgres_host": "127.0.0.1"},
        {"postgres_host": "db.example.com/path"},
        {"postgres_host": "db.example.com:5432"},
        {"postgres_host": "user@db.example.com"},
        {"postgres_dbname": "postgresql://evil"},
        {"postgres_user": "bad\0name"},
        {"postgres_password": "bad\0password"},
        {"postgres_port": 80},
        {"supabase_project_ref": "../../admin"},
        {"vercel_deployment_id": "https://evil.example"},
        {"vercel_token": "key\nvalue"},
        {"environment": "production", "infrastructure_mode": "fixture"},
        {"infrastructure_dns_nameservers": ["127.0.0.1"]},
    ],
)
def test_operator_configuration_rejects_unsafe_settings(kwargs):
    with pytest.raises(ValidationError):
        config(**kwargs)


def test_empty_example_values_and_secrets_are_safe():
    settings = config(
        vercel_token="",
        vercel_deployment_id="",
        vercel_team_id="",
        supabase_access_token="",
        supabase_project_ref="",
        postgres_host="",
        postgres_dbname="",
        postgres_user="",
        postgres_password="",
    )
    assert settings.postgres_host is None and settings.postgres_password is None
    assert not any(
        row["configured"] for row in InfrastructureService(settings).describe()["checks"]
    )
    assert TOKEN not in repr(config(vercel_token=TOKEN, postgres_password=TOKEN))


def test_database_port_loads_from_environment(monkeypatch):
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    assert config().postgres_port == 6543


def test_only_fixed_provider_paths_are_available():
    client = make_client(lambda _: pytest.fail("Unexpected request"))
    with pytest.raises(InfrastructureError, match="invalid_request"):
        asyncio.run(client.get("/v13/deployments/../secrets"))
    with pytest.raises(ValueError):
        asyncio.run(InfrastructureService(config()).check("arbitrary-url"))


def test_check_failure_has_no_raw_provider_exception_text():
    client = AsyncMock()
    client.get.side_effect = InfrastructureError("access_denied")
    service = InfrastructureService(
        config(infrastructure_mode="live", vercel_deployment_id=DEPLOYMENT_ID), vercel=client
    )
    assert asyncio.run(service.check("vercel-deployment")).evidence == {}
