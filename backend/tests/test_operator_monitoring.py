import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.db.migrate import downgrade
from app.main import create_app
from app.tools.models import CheckResult


def checker():
    value = AsyncMock()
    for name, kind in (("check_http", "http"), ("check_dns", "dns"), ("check_ssl", "ssl")):

        async def check(target, kind=kind):
            return CheckResult(
                component=target.id, check_type=kind, status="HEALTHY", summary="Checked"
            )

        getattr(value, name).side_effect = check
    return value


def test_registration_survives_restart_and_is_available_to_agent(database_config, engine):
    app = create_app(database_config, website_checker=checker())
    with TestClient(app) as client:
        first = client.post("/monitoring/websites", json={"url": "https://example.com/health"})
        assert first.status_code == 200
        target = first.json()
        assert target["id"].startswith("site-")
        assert client.post("/monitoring/websites", json={"url": target["url"]}).json() == target
        assert client.get("/monitoring").json()["automatic_monitoring"] is False
        assert len(client.get("/services/websites").json()) == 1
        result = client.post(f"/monitoring/websites/{target['id']}/checks").json()
        assert len(result["results"]) == 3
        assert all(item["history"]["status"] == "saved" for item in result["results"])
        assert len(client.get("/history/checks").json()) == 3
    reopened = create_app(database_config)
    with TestClient(reopened) as client:
        assert client.get("/services/websites").json() == [
            {"id": target["id"], "url": target["url"]}
        ]
        registry = reopened.state.tool_registry
        listed = asyncio.run(registry.execute("list_website_targets", "{}"))
        assert listed.data["targets"] == [{"id": target["id"]}]
        rejected = asyncio.run(registry.execute("check_dns", json.dumps({"target_id": "unknown"})))
        assert rejected.reason == "target_not_registered"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "https://user:pass@example.com",
        "https://example.com/?secret=x",
        "https://example.com/#secret",
    ],
)
def test_operator_registration_rejects_unsafe_destinations(url):
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.post("/monitoring/websites", json={"url": url})
        assert response.status_code == 422
        assert url not in response.text


def test_registration_does_not_contact_target_and_enforces_boundaries(database_config, engine):
    adapter = checker()
    with TestClient(create_app(database_config, website_checker=adapter)) as client:
        assert (
            client.post("/monitoring/websites", json={"url": "https://example.com"}).status_code
            == 200
        )
        adapter.check_http.assert_not_awaited()
        assert (
            client.post(
                "/monitoring/websites", json={"url": "https://example.com", "token": "secret"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/monitoring/websites",
                content='{"url":"https://example.com","url":"https://other.example"}',
                headers={"content-type": "application/json"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/monitoring/websites",
                content="x" * 4097,
                headers={"content-type": "application/json"},
            ).status_code
            == 413
        )
        assert client.post("/monitoring/websites", content="{}").status_code == 415
        assert client.post("/monitoring/websites/not-registered/checks").status_code == 404
        app_targets = client.app.state.operator_targets
        app_targets.check_busy = True
        assert client.post("/monitoring/websites/not-registered/checks").status_code == 409
        app_targets.check_busy = False


def test_saved_configuration_is_bounded_and_preserved_on_downgrade(database_config, engine):
    with TestClient(create_app(database_config)) as client:
        for number in range(25):
            assert (
                client.post(
                    "/monitoring/websites", json={"url": f"https://example.com/{number}"}
                ).status_code
                == 200
            )
        assert (
            client.post(
                "/monitoring/websites", json={"url": "https://example.com/extra"}
            ).status_code
            == 409
        )
        assert (
            client.post("/monitoring/websites", json={"url": "https://example.com/0"}).status_code
            == 200
        )
    with pytest.raises(RuntimeError, match="Saved website targets"):
        downgrade(engine, "0005_verified_recovery")


def test_registration_requires_storage_and_production_authentication():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert (
            client.post("/monitoring/websites", json={"url": "https://example.com"}).status_code
            == 503
        )
    config = Settings(
        _env_file=None,
        environment="production",
        api_access_token=SecretStr("x" * 43),
        api_allowed_hosts=["testserver"],
    )
    with TestClient(create_app(config)) as client:
        assert client.get("/monitoring").status_code == 401
        assert (
            client.post("/monitoring/websites", json={"url": "https://example.com"}).status_code
            == 401
        )
        assert client.post("/monitoring/websites/x/checks").status_code == 401
        assert (
            client.get(
                "/monitoring",
                headers={"Authorization": "Bearer " + "x" * 43, "Origin": "https://evil.example"},
            ).status_code
            == 401
        )
