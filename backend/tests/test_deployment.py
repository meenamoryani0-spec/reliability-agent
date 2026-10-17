import asyncio
import os
import re
import threading
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import certifi
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.safety import configured_secrets
from app.config import Settings
from app.db.database import create_storage_engine
from app.main import create_app

# Disposable values, never deployment credentials.
TOKEN = "phase14_test_only_" + "a" * 32


def config(**changes):
    return Settings(
        _env_file=None,
        environment="production",
        api_access_token=TOKEN,
        api_allowed_hosts=["testserver"],
        **changes,
    )


@pytest.mark.parametrize(
    "path,method",
    [
        ("/services/websites", "get"),
        ("/checks/websites/unconfigured", "post"),
        ("/services/browser-flows", "get"),
        ("/services/n8n", "get"),
        ("/n8n/executions/1001", "get"),
        ("/services/infrastructure", "get"),
        ("/checks/infrastructure/postgres", "post"),
        ("/history/checks", "get"),
        ("/storage", "get"),
        ("/agent", "get"),
        ("/tools", "get"),
        ("/investigations", "post"),
        ("/actions", "get"),
        ("/recovery", "get"),
    ],
)
def test_every_operation_authenticates_before_adapter_access(path, method):
    service = AsyncMock()
    app = create_app(config(), infrastructure_service=service)
    service.reset_mock()  # Construction checks the injected adapter's truth value.
    with TestClient(app) as client:
        response = getattr(client, method)(path)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert "access-control-allow-origin" not in response.headers
        assert TOKEN not in response.text
        assert not service.mock_calls


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer invalid"},
        {"Authorization": f"bearer {TOKEN}"},
        {"Authorization": f"Bearer {TOKEN}", "Origin": "https://dashboard.example"},
        [("Authorization", f"Bearer {TOKEN}"), ("Authorization", f"Bearer {TOKEN}")],
        {"X-Forwarded-Authorization": f"Bearer {TOKEN}"},
        {"Cookie": f"access_token={TOKEN}"},
    ],
)
def test_ambiguous_or_browser_credentials_fail_closed(headers):
    with TestClient(create_app(config())) as client:
        assert client.get("/agent", headers=headers).status_code == 401


def test_authenticated_production_reads_and_no_remediation():
    app = create_app(config())
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        assert client.get("/agent").json()["mode"] == "disabled"
        assert client.get("/services/websites").json() == []
        assert client.get("/storage").json()["mode"] == "disabled"
        assert client.get("/history/checks").status_code == 503
        assert client.get("/services/n8n").status_code == 200
        assert client.get("/services/infrastructure").status_code == 200
        assert client.get("/actions").json()["mode"] == "disabled"
        assert client.get("/recovery").json()["mode"] == "disabled"
        tools = client.get("/tools").json()["tools"]
        assert len(tools) == 12
        assert "test_website_flow" not in {tool["function"]["name"] for tool in tools}
        rejected = client.portal.call(app.state.tool_registry.execute, "test_website_flow", "{}")
        assert rejected.status == "REJECTED"
        assert client.get("/services/browser-flows").status_code == 404
        for path in (
            "/actions/approve",
            "/actions/execute",
            "/recovery/verify",
            "/incidents/resolve",
        ):
            assert client.post(path).status_code == 404
        for path in ("/docs", "/openapi.json"):
            assert client.get(path).status_code == 404


def test_all_production_hosts_are_exact_and_forwarded_headers_cannot_override():
    with TestClient(create_app(config())) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400
        assert (
            client.get(
                "/health", headers={"Host": "evil.example", "X-Forwarded-Host": "testserver"}
            ).status_code
            == 400
        )
        assert (
            client.options("/agent", headers={"Origin": "https://evil.example"}).status_code == 401
        )


def test_missing_access_is_locked_and_cannot_be_ready():
    with TestClient(create_app(Settings(_env_file=None, environment="production"))) as client:
        assert client.get("/services/websites").status_code == 404
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/ready").status_code == 503
        assert client.get("/ready").json() == {"status": "not_ready"}


def test_readiness_verifies_schema_without_running_migrations(database_config, engine):
    app = create_app(database_config)
    with TestClient(app) as client:
        assert client.get("/ready").json() == {"status": "ready"}
        assert client.get("/ready").status_code == 200


def test_readiness_does_not_create_schema(database_config):
    app = create_app(database_config)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert app.state.history.state == "migration_required"


def test_readiness_deduplicates_workers_and_drains_after_timeout():
    app = create_app(Settings(_env_file=None))
    history = app.state.history
    release, entered = threading.Event(), threading.Event()
    history.engine = Mock()

    def blocked_verify():
        entered.set()
        release.wait(timeout=10)
        return True

    history.verify = Mock(side_effect=blocked_verify)

    async def run():
        first = asyncio.create_task(history.readiness())
        await asyncio.to_thread(entered.wait, 2)
        second = asyncio.create_task(history.readiness())
        await asyncio.sleep(0)
        assert history.verify.call_count == 1
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not history._readiness_task.done()
        release.set()
        assert await second
        await history.close()

    asyncio.run(run())


def test_authenticated_request_budget_is_bounded():
    with (
        patch("app.security.time.monotonic", return_value=100),
        TestClient(create_app(config()), headers={"Authorization": f"Bearer {TOKEN}"}) as client,
    ):
        for _ in range(120):
            assert client.get("/agent").status_code == 200
        assert client.get("/agent").status_code == 429
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize("token", ["short", "x" * 129, "a" * 42, "a" * 43 + "\n"])
def test_weak_or_malformed_access_tokens_rejected_without_echo(token):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, api_access_token=token)
    assert token not in str(error.value)


@pytest.mark.parametrize("host", ["*", "https://api.example", "API.example", "a..b", "a/b"])
def test_unsafe_host_configuration_rejected(host):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_allowed_hosts=[host])


def test_access_key_is_masked_and_part_of_model_echo_guard():
    settings = config(incidents_enabled=True)
    assert TOKEN not in repr(settings)
    assert TOKEN not in settings.model_dump_json()
    assert TOKEN in configured_secrets(settings)
    assert settings.operations_access_enabled
    assert settings.n8n_retry_mode == settings.n8n_recovery_mode == "disabled"


def test_storage_custom_ca_preserves_hostname_verification(tmp_path):
    authority = re.search(
        rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        Path(certifi.where()).read_bytes(),
        re.DOTALL,
    ).group()
    certificate = tmp_path / "project-ca.pem"
    certificate.write_bytes(authority)
    settings = config(
        storage_mode="postgresql",
        storage_database_url="postgresql+psycopg://operator:disposable@db.example/app",
        storage_ssl_ca_file=str(certificate),
    )
    with patch("app.db.database.create_engine") as factory:
        create_storage_engine(settings)
    args = factory.call_args.kwargs["connect_args"]
    assert args["sslmode"] == "verify-full"
    assert args["sslrootcert"] == str(certificate)


@pytest.mark.parametrize("value", ["relative-ca.pem", "/nonexistent-phase14-ca.pem"])
def test_storage_ca_requires_existing_absolute_certificate(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, storage_ssl_ca_file=value)


@pytest.mark.parametrize(
    "content", [b"not a certificate", b"x" * 131073], ids=["invalid", "oversized"]
)
def test_storage_ca_invalid_or_oversized_files_fail_closed(tmp_path, content):
    certificate = tmp_path / "invalid.pem"
    certificate.write_bytes(content)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, storage_ssl_ca_file=str(certificate))


@pytest.mark.parametrize("settings", [Settings(_env_file=None), config()])
def test_production_entry_rejects_incomplete_release_before_binding(settings):
    from app.serve import main

    with patch("app.serve.Settings", return_value=settings), patch("app.serve.uvicorn.run") as run:
        with pytest.raises(SystemExit):
            main()
        run.assert_not_called()


def test_production_entry_uses_one_bounded_worker_and_no_proxy_trust(monkeypatch):
    from app.serve import main

    settings = config(
        storage_mode="postgresql",
        storage_database_url="postgresql+psycopg://operator:disposable@db.example/app",
    )
    monkeypatch.setenv("PORT", "8181")
    with patch("app.serve.Settings", return_value=settings), patch("app.serve.uvicorn.run") as run:
        main()
    options = run.call_args.kwargs
    assert options["workers"] == 1 and options["port"] == 8181
    assert options["limit_concurrency"] == 64
    assert options["timeout_graceful_shutdown"] == 180
    assert options["proxy_headers"] is options["access_log"] is False


def test_render_assigned_host_is_exact_and_does_not_trust_request_headers(monkeypatch):
    from app.serve import configure_platform_host

    monkeypatch.delenv("API_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "assigned-service-123.onrender.com")
    configure_platform_host()
    settings = Settings(_env_file=None, environment="production", api_access_token=TOKEN)
    with TestClient(create_app(settings)) as client:
        assert (
            client.get("/health", headers={"Host": "assigned-service-123.onrender.com"}).status_code
            == 200
        )
        assert (
            client.get("/health", headers={"Host": "another-service.onrender.com"}).status_code
            == 400
        )
        assert (
            client.get(
                "/health",
                headers={
                    "Host": "evil.example",
                    "X-Forwarded-Host": "assigned-service-123.onrender.com",
                },
            ).status_code
            == 400
        )


@pytest.mark.parametrize("explicit", ['["custom.example"]', "[]", "malformed"])
def test_render_metadata_never_overwrites_explicit_host_configuration(monkeypatch, explicit):
    from app.serve import configure_platform_host

    monkeypatch.setenv("API_ALLOWED_HOSTS", explicit)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "assigned-service.onrender.com")
    configure_platform_host()
    assert os.environ["API_ALLOWED_HOSTS"] == explicit


@pytest.mark.parametrize("render", [None, "false", "True"])
def test_render_host_fallback_is_inactive_outside_render(monkeypatch, render):
    from app.serve import configure_platform_host

    monkeypatch.delenv("API_ALLOWED_HOSTS", raising=False)
    if render is None:
        monkeypatch.delenv("RENDER", raising=False)
    else:
        monkeypatch.setenv("RENDER", render)
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "assigned-service.onrender.com")
    configure_platform_host()
    assert "API_ALLOWED_HOSTS" not in os.environ


@pytest.mark.parametrize(
    "hostname",
    [
        "",
        "evil.example",
        "*.onrender.com",
        "https://service.onrender.com",
        "service.onrender.com:443",
        "SERVICE.onrender.com",
        "service.onrender.com.evil.example",
        "service.onrender.com\n",
    ],
)
def test_invalid_render_metadata_stops_before_binding(monkeypatch, hostname):
    from app.serve import main

    monkeypatch.delenv("API_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", hostname)
    with patch("app.serve.uvicorn.run") as run:
        with pytest.raises(SystemExit, match="exact assigned service hostname"):
            main()
        run.assert_not_called()
