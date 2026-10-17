from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tools.infrastructure_models import CHECK_IDS


def test_fixture_checks_through_api_are_explicit_and_redacted():
    with TestClient(create_app(Settings(_env_file=None, infrastructure_mode="fixture"))) as client:
        registry = client.get("/services/infrastructure").json()
        assert registry["synthetic"] and all(row["configured"] for row in registry["checks"])
        for check in CHECK_IDS:
            response = client.post("/checks/infrastructure/" + check)
            assert response.status_code == 200
            result = response.json()
            assert result["component"] == check and result["inspection"] == "OK"
            assert result["synthetic"] and not result["business_outcome_verified"]
            assert "SYNTHETIC_PRIVATE" not in response.text
        assert client.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize(
    "mode,reason", [("disabled", "integration_disabled"), ("live", "missing_configuration")]
)
def test_unconfigured_checks_preserve_backend_liveness(mode, reason):
    with TestClient(create_app(Settings(_env_file=None, infrastructure_mode=mode))) as client:
        for check in CHECK_IDS:
            result = client.post("/checks/infrastructure/" + check).json()
            assert result["healthy"] is None and result["reason"] == reason
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize("mode", ["disabled", "live"])
def test_production_checks_are_disabled_before_adapter_calls(mode):
    service = AsyncMock()
    with TestClient(
        create_app(
            Settings(_env_file=None, environment="production", infrastructure_mode=mode),
            infrastructure_service=service,
        )
    ) as client:
        assert client.get("/services/infrastructure").status_code == 404
        for check in CHECK_IDS:
            assert client.post("/checks/infrastructure/" + check).status_code == 404
        service.check.assert_not_called()


def test_api_cannot_select_urls_sql_or_write_operations(client):
    for unknown in ["retry", "redeploy", "query", "delete", "arbitrary"]:
        assert client.post("/checks/infrastructure/" + unknown).status_code == 404
    assert client.get("/checks/infrastructure/postgres").status_code == 405
    assert client.delete("/checks/infrastructure/postgres").status_code == 405
    paths = client.get("/openapi.json").json()["paths"]
    operation = paths["/checks/infrastructure/{check_id}"]["post"]
    assert "requestBody" not in operation
    assert [row["name"] for row in operation["parameters"]] == ["check_id"]
