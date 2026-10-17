import asyncio
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.agent.tool_registry import MAX_ARGUMENT_BYTES, MAX_RESULT_BYTES
from app.config import PROJECT_ROOT, Settings
from app.db.capture import HistoryCapture
from app.db.database import create_storage_engine
from app.db.migrate import upgrade
from app.main import create_app
from app.tools.browser_models import BrowserEvidence, BrowserFlowResult
from app.tools.models import CheckResult, WebsiteTarget
from app.tools.n8n_models import N8nReadResult


def configured_app(**options):
    settings = options.pop("settings", None) or Settings(
        _env_file=None,
        environment="test",
        n8n_mode="fixture",
        infrastructure_mode="fixture",
        website_targets=[WebsiteTarget(id="demo", url="https://example.com/health")],
    )
    return create_app(settings, **options)


def short_deadline(registry, name):
    specs = dict(registry._specs)
    specs[name] = replace(specs[name], timeout_seconds=0.02)
    registry._specs = MappingProxyType(specs)


def test_catalog_has_exact_tools_strict_schemas_and_no_destinations():
    app = configured_app()
    with TestClient(app) as client:
        response = client.get("/tools")
        assert response.status_code == 200
        catalog = response.json()
        tools = {tool["function"]["name"]: tool["function"] for tool in catalog["tools"]}
        assert set(tools) == {
            "list_website_targets",
            "check_website_http",
            "check_dns",
            "check_ssl",
            "test_website_flow",
            "list_n8n_workflows",
            "list_failed_n8n_executions",
            "get_n8n_execution",
            "check_vercel_deployment",
            "get_vercel_deployment_events",
            "check_supabase_project",
            "check_supabase_health",
            "check_postgres",
        }
        assert all(tool["parameters"]["additionalProperties"] is False for tool in tools.values())
        assert tools["check_dns"]["parameters"]["properties"]["target_id"]["enum"] == ["demo"]
        assert tools["get_n8n_execution"]["parameters"]["required"] == ["execution_id"]
        assert tools["list_n8n_workflows"]["parameters"]["properties"]["limit"]["maximum"] == 50
        assert "https://example.com" not in response.text
        assert catalog["policy"]["monitored_system_writes"] is False
        assert catalog["policy"]["max_in_flight"] == 1
        assert client.post("/tools", json={}).status_code == 405
        assert client.post("/tools/execute", json={}).status_code == 404
        definitions = app.state.tool_registry.definitions()
        definitions[0]["function"]["parameters"]["properties"]["url"] = {}
        assert (
            "url"
            not in app.state.tool_registry.definitions()[0]["function"]["parameters"]["properties"]
        )


@pytest.mark.parametrize(
    "name",
    [
        "shell",
        "retry_n8n_execution",
        "create_incident",
        "resolve_incident",
        "sql",
        "https://evil.example",
        "check_postgres\n",
        "__dict__",
        None,
        {},
    ],
)
def test_unknown_tools_rejected_without_dispatch(name):
    adapter = AsyncMock()
    app = configured_app(infrastructure_service=adapter)
    result = asyncio.run(app.state.tool_registry.execute(name, "{}"))
    assert result.status == "REJECTED" and result.reason == "unknown_tool" and result.name is None
    adapter.check.assert_not_awaited()


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("check_postgres", '{"sql":"DROP TABLE checks"}'),
        ("check_postgres", '{"host":"localhost"}'),
        ("check_vercel_deployment", '{"deployment_id":"dpl_other"}'),
        ("check_website_http", '{"target_id":"https://example.com"}'),
        ("check_dns", '{"target_id":"demo","url":"http://127.0.0.1"}'),
        ("test_website_flow", '{"flow_id":"custom"}'),
        ("get_n8n_execution", '{"execution_id":1001}'),
        ("get_n8n_execution", '{"execution_id":"../credentials"}'),
        ("get_n8n_execution", '{"execution_id":"0"}'),
        ("get_n8n_execution", "{}"),
        ("list_failed_n8n_executions", '{"workflow_id":"wf/other"}'),
        ("list_n8n_workflows", '{"limit":true}'),
        ("list_n8n_workflows", '{"limit":"5"}'),
        ("list_n8n_workflows", '{"limit":1.0}'),
        ("list_n8n_workflows", '{"limit":0}'),
        ("list_n8n_workflows", '{"limit":51}'),
        ("list_n8n_workflows", '{"cursor":"https://evil.example/"}'),
        ("list_n8n_workflows", '{"limit":1,"limit":2}'),
        ("list_n8n_workflows", '{"limit":NaN}'),
        ("list_n8n_workflows", '{"limit":Infinity}'),
        ("check_postgres", "null"),
        ("check_postgres", "[]"),
        ("check_postgres", "{} trailing"),
        ("check_postgres", ""),
        ("check_postgres", {}),
        ("check_postgres", "[" * 1500 + "]" * 1500),
        ("check_postgres", "\ud800"),
    ],
)
def test_invalid_arguments_fail_before_any_io(name, arguments):
    website, n8n, infra, browser = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    app = configured_app(
        website_checker=website,
        n8n_service=n8n,
        infrastructure_service=infra,
        browser_checker=browser,
    )
    for adapter in (website, n8n, infra, browser):
        adapter.reset_mock()  # App construction tests adapter truthiness; that is not I/O.
    result = asyncio.run(app.state.tool_registry.execute(name, arguments))
    assert result.status == "REJECTED" and result.reason == "invalid_arguments"
    for adapter in (website, n8n, infra, browser):
        assert adapter.mock_calls == []
    assert "DROP TABLE" not in result.model_dump_json()


@pytest.mark.parametrize("arguments", [" " * (MAX_ARGUMENT_BYTES + 1), '"' + "é" * 2100 + '"'])
def test_argument_budget_counts_utf8_bytes(arguments):
    result = asyncio.run(configured_app().state.tool_registry.execute("check_postgres", arguments))
    assert result.reason == "arguments_too_large"


def test_unregistered_target_is_rejected_before_io():
    checker = AsyncMock()
    app = configured_app(website_checker=checker)
    checker.reset_mock()
    result = asyncio.run(app.state.tool_registry.execute("check_dns", '{"target_id":"other"}'))
    assert result.reason == "target_not_registered"
    assert checker.mock_calls == []


@pytest.mark.parametrize(
    "name,method,kind",
    [
        ("check_website_http", "check_http", "http"),
        ("check_dns", "check_dns", "dns"),
        ("check_ssl", "check_ssl", "ssl"),
    ],
)
def test_website_dispatch_and_evidence_projection(name, method, kind):
    checker = AsyncMock()
    getattr(checker, method).return_value = CheckResult(
        component="demo",
        check_type=kind,
        status="HEALTHY",
        summary="PRIVATE",
        latency_ms=12.5,
        severity="none",
        evidence={"http_status": 200, "raw_body": "PRIVATE"},
    )
    registry = configured_app(website_checker=checker).state.tool_registry
    result = asyncio.run(registry.execute(name, '{"target_id":"demo"}'))
    assert result.status == "OK" and result.data["status"] == "HEALTHY"
    assert result.data["synthetic"] is False
    assert result.data["latency_ms"] == 12.5 and result.data["severity"] == "none"
    assert result.history.status == "disabled"
    assert "PRIVATE" not in result.model_dump_json()
    getattr(checker, method).assert_awaited_once_with(registry._targets["demo"])


@pytest.mark.parametrize(
    "name,arguments,expected",
    [
        ("list_website_targets", "{}", None),
        ("list_n8n_workflows", "{}", None),
        ("list_failed_n8n_executions", '{"workflow_id":"wf-booking"}', None),
        ("get_n8n_execution", '{"execution_id":"1001"}', "UNHEALTHY"),
        ("get_n8n_execution", '{"execution_id":"1002"}', "HEALTHY"),
        ("check_vercel_deployment", "{}", "UNHEALTHY"),
        ("get_vercel_deployment_events", "{}", "UNKNOWN"),
        ("check_supabase_project", "{}", "HEALTHY"),
        ("check_supabase_health", "{}", "HEALTHY"),
        ("check_postgres", "{}", "HEALTHY"),
    ],
)
def test_real_fixture_adapters_keep_health_and_inspection_distinct(name, arguments, expected):
    result = asyncio.run(configured_app().state.tool_registry.execute(name, arguments))
    assert result.status == "OK"
    assert len(result.model_dump_json().encode()) <= MAX_RESULT_BYTES
    if expected:
        assert result.data["status"] == expected
        assert result.data["synthetic"] is True
        assert result.data["root_cause_verified"] is False
        assert result.data["business_outcome_verified"] is False
    else:
        assert result.history.status == "not_applicable"
    assert "SYNTHETIC_PRIVATE_DATA_DO_NOT_RETURN" not in result.model_dump_json()
    if name == "get_n8n_execution" and expected == "UNHEALTHY":
        failures = result.data["evidence"]["failures"]
        assert failures[0]["http_status"] == 401
        assert failures[0]["category"] == "authentication_rejected"


def test_browser_keeps_synthetic_label():
    checker = AsyncMock()
    checker.check.return_value = BrowserFlowResult(
        component="booking-healthy",
        status="HEALTHY",
        summary="Fixture",
        evidence=BrowserEvidence(reason="confirmation_verified", confirmation_visible=True),
    )
    result = asyncio.run(
        configured_app(browser_checker=checker).state.tool_registry.execute(
            "test_website_flow", '{"flow_id":"booking-healthy"}'
        )
    )
    assert result.data["synthetic"] is True
    assert result.data["evidence"]["network_mode"] == "intercepted_local_fixtures"


def test_disabled_adapters_remain_check_failed_not_unhealthy():
    registry = configured_app(
        settings=Settings(_env_file=None, environment="test")
    ).state.tool_registry

    async def run():
        for name, args in [
            ("check_postgres", "{}"),
            ("get_n8n_execution", '{"execution_id":"1001"}'),
        ]:
            result = await registry.execute(name, args)
            assert result.status == "OK"
            assert result.data["status"] == "CHECK_FAILED"
            assert result.data["reason"] == "integration_disabled"
            assert result.data["synthetic"] is False

    asyncio.run(run())


def test_tool_and_api_observations_share_persistent_identities(tmp_path):
    config = Settings(
        _env_file=None,
        environment="test",
        n8n_mode="fixture",
        infrastructure_mode="fixture",
        storage_mode="local",
        storage_sqlite_file=str((tmp_path / "tools.sqlite3").relative_to(PROJECT_ROOT)),
    )
    engine = create_storage_engine(config)
    upgrade(engine)
    engine.dispose()
    app = configured_app(settings=config)
    with TestClient(app) as client:
        client.post("/checks/infrastructure/vercel-deployment")
        client.get("/n8n/executions/1001")

        async def run():
            for name, args in [
                ("check_vercel_deployment", "{}"),
                ("get_n8n_execution", '{"execution_id":"1001"}'),
            ]:
                result = await app.state.tool_registry.execute(name, args)
                assert result.history.status == "saved"
                assert result.history.check_id
            await app.state.tool_registry.execute("list_n8n_workflows", "{}")

        client.portal.call(run)
        assert len(client.get("/history/services").json()) == 2
        assert len(client.get("/history/checks").json()) == 4
        assert client.get("/history/incidents").json() == []


def test_storage_exception_preserves_observation_and_hides_details():
    app = configured_app()
    app.state.tool_registry._history = Mock(
        capture=AsyncMock(side_effect=RuntimeError("SECRET_DB_URL"))
    )
    result = asyncio.run(app.state.tool_registry.execute("check_postgres", "{}"))
    assert result.status == "OK" and result.data["status"] == "HEALTHY"
    assert result.history.status == "unavailable"
    assert "SECRET_DB_URL" not in result.model_dump_json()


def test_missing_migration_preserves_registry_observation(tmp_path):
    config = Settings(
        _env_file=None,
        environment="test",
        infrastructure_mode="fixture",
        storage_mode="local",
        storage_sqlite_file=str((tmp_path / "unmigrated.sqlite3").relative_to(PROJECT_ROOT)),
    )
    app = configured_app(settings=config)

    async def run():
        try:
            result = await app.state.tool_registry.execute("check_postgres", "{}")
            assert result.status == "OK" and result.data["status"] == "HEALTHY"
            assert result.history.status == "unavailable" and result.history.check_id is None
        finally:
            await app.state.tool_registry.close()
            await app.state.history.close()

    asyncio.run(run())


def test_pagination_returns_one_page_and_forwards_only_validated_arguments():
    service = Mock(
        read=AsyncMock(
            return_value=N8nReadResult(
                operation="failed_executions",
                status="OK",
                synthetic=True,
                next_cursor="next-page",
            )
        )
    )
    registry = configured_app(n8n_service=service).state.tool_registry
    result = asyncio.run(
        registry.execute(
            "list_failed_n8n_executions",
            '{"limit":50,"cursor":"current-page","workflow_id":"wf-booking"}',
        )
    )
    assert result.status == "OK" and result.data["next_cursor"] == "next-page"
    assert result.history.status == "not_applicable"
    service.read.assert_awaited_once_with(
        "failed_executions",
        limit=50,
        cursor="current-page",
        workflow_id="wf-booking",
    )


@pytest.mark.parametrize("latency", [-1, float("inf"), float("nan")])
def test_invalid_latency_is_not_silently_serialized_as_healthy(latency):
    checker = AsyncMock()
    checker.check_http.return_value = CheckResult(
        component="demo",
        check_type="http",
        status="HEALTHY",
        summary="ignored",
        latency_ms=latency,
    )
    registry = configured_app(website_checker=checker).state.tool_registry
    result = asyncio.run(registry.execute("check_website_http", '{"target_id":"demo"}'))
    assert result.reason == "invalid_result" and result.data is None


def test_adapter_exception_does_not_echo_secrets_or_diagnose_health():
    adapter = Mock(check=AsyncMock(side_effect=RuntimeError("SECRET_TOKEN")))
    result = asyncio.run(
        configured_app(infrastructure_service=adapter).state.tool_registry.execute(
            "check_postgres", "{}"
        )
    )
    assert result.status == "EXECUTION_FAILED" and result.data is None
    assert result.reason == "execution_failed"
    assert "SECRET_TOKEN" not in result.model_dump_json()


@pytest.mark.parametrize("secret", ['quoted"secret', "backslash\\secret", "unicode-é-secret"])
def test_json_escaping_cannot_hide_secret_echoes(secret):
    config = Settings(
        _env_file=None,
        environment="test",
        postgres_password=SecretStr(secret),
        website_targets=[WebsiteTarget(id="demo", url="https://example.com")],
    )
    checker = AsyncMock()
    checker.check_http.return_value = CheckResult(
        component="demo",
        check_type="http",
        status="UNKNOWN",
        summary="ignored",
        evidence={"reason": secret},
    )
    registry = configured_app(settings=config, website_checker=checker).state.tool_registry
    result = asyncio.run(registry.execute("check_website_http", '{"target_id":"demo"}'))
    assert result.reason == "unsafe_result" and result.data is None


@pytest.mark.parametrize(
    "evidence,reason",
    [
        ({"reason": "x" * 66000}, "invalid_result"),
        ({"reason": "x" * 65000}, "result_too_large"),
        ({"reason": "registry-secret"}, "unsafe_result"),
    ],
)
def test_output_budgets_and_secret_echo_fail_closed(evidence, reason):
    checker = AsyncMock()
    checker.check_http.return_value = CheckResult(
        component="demo", check_type="http", status="UNKNOWN", summary="ignored", evidence=evidence
    )
    config = Settings(
        _env_file=None,
        environment="test",
        nebius_api_key=SecretStr("registry-secret"),
        website_targets=[WebsiteTarget(id="demo", url="https://example.com")],
    )
    registry = configured_app(settings=config, website_checker=checker).state.tool_registry
    registry._history = Mock(capture=AsyncMock())
    result = asyncio.run(registry.execute("check_website_http", '{"target_id":"demo"}'))
    assert result.status == "EXECUTION_FAILED" and result.reason == reason
    assert result.data is None
    registry._history.capture.assert_not_awaited()


def test_deadline_and_cancellation_keep_slot_until_actual_work_finishes():
    async def run():
        release = asyncio.Event()
        entered = asyncio.Event()

        async def slow(_):
            entered.set()
            await release.wait()
            raise RuntimeError("private")

        adapter = Mock(check=slow)
        registry = configured_app(infrastructure_service=adapter).state.tool_registry
        short_deadline(registry, "check_postgres")
        result = await registry.execute("check_postgres", "{}")
        assert result.reason == "deadline_exceeded" and result.data is None
        assert (await registry.execute("list_website_targets", "{}")).reason == "busy"
        release.set()
        await registry._task
        assert (await registry.execute("list_website_targets", "{}")).status == "OK"
        release.clear()
        entered.clear()
        caller = asyncio.create_task(registry.execute("check_postgres", "{}"))
        await entered.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert (await registry.execute("check_postgres", "{}")).reason == "busy"
        closing = asyncio.create_task(registry.close())
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        await closing
        assert (await registry.execute("check_postgres", "{}")).reason == "access_disabled"

    asyncio.run(run())


def test_slow_storage_returns_observation_while_slot_stays_busy():
    async def run():
        release = asyncio.Event()

        async def capture(*_):
            await release.wait()
            return HistoryCapture(status="disabled")

        registry = configured_app().state.tool_registry
        registry._history = Mock(capture=capture)
        short_deadline(registry, "check_postgres")
        result = await registry.execute("check_postgres", "{}")
        assert result.status == "OK" and result.data["status"] == "HEALTHY"
        assert result.history.status == "unavailable"
        assert (await registry.execute("check_postgres", "{}")).reason == "busy"
        release.set()
        await registry.close()

    asyncio.run(run())


def test_production_rejects_catalog_and_internal_execution():
    app = configured_app(settings=Settings(_env_file=None, environment="production"))
    with TestClient(app) as client:
        assert client.get("/tools").status_code == 404
        assert app.state.tool_registry.definitions() == []
        result = client.portal.call(app.state.tool_registry.execute, "list_website_targets", "{}")
        assert result.reason == "access_disabled"


@pytest.mark.parametrize("timed_out", [False, True])
@pytest.mark.parametrize(
    "enabled,tool,arguments,expected",
    [
        (True, "get_n8n_execution", '{"execution_id":"1001"}', "unavailable"),
        (True, "check_postgres", "{}", "not_applicable"),
        (False, "get_n8n_execution", '{"execution_id":"1001"}', "disabled"),
    ],
)
def test_uncertain_storage_does_not_claim_incident_detection_is_inapplicable(
    timed_out, enabled, tool, arguments, expected
):
    async def run():
        release = asyncio.Event()

        async def capture(*_):
            if timed_out:
                await release.wait()
            raise RuntimeError("PRIVATE_STORAGE_DETAILS")

        registry = configured_app(
            settings=Settings(
                _env_file=None,
                environment="test",
                incidents_enabled=enabled,
                n8n_mode="fixture",
                infrastructure_mode="fixture",
            )
        ).state.tool_registry
        registry._history = Mock(capture=capture)
        # Allow the real fixture adapter to reach storage on a loaded Windows
        # runner. The event keeps storage blocked deterministically thereafter.
        specs = dict(registry._specs)
        specs[tool] = replace(specs[tool], timeout_seconds=1)
        registry._specs = MappingProxyType(specs)
        try:
            result = await registry.execute(tool, arguments)
            assert result.status == "OK" and result.history.status == "unavailable"
            assert result.history.incident.status == expected
            assert result.history.incident.incident_id is None
            assert "PRIVATE_STORAGE_DETAILS" not in result.model_dump_json()
            if timed_out:
                assert (await registry.execute(tool, arguments)).reason == "busy"
        finally:
            release.set()
            await registry.close()

    asyncio.run(run())
