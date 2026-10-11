import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.tools.n8n_fixtures import PRIVATE_CANARY


@pytest.fixture
def fixture_api():
    with TestClient(
        create_app(Settings(_env_file=None, environment="test", n8n_mode="fixture"))
    ) as client:
        yield client


def test_fixture_registry_and_reads(fixture_api):
    assert fixture_api.get("/services/n8n").json() == {
        "mode": "fixture",
        "configured": True,
        "synthetic": True,
    }
    workflows = fixture_api.get("/n8n/workflows").json()
    assert workflows["workflows"] == [{"id": "wf-booking", "active": True}]
    failed = fixture_api.get("/n8n/executions/failed?workflow_id=wf-booking").json()
    assert [record["id"] for record in failed["executions"]] == ["1001"]
    for identifier in ("1001", "1002"):
        response = fixture_api.get(f"/n8n/executions/{identifier}")
        assert response.status_code == 200
        assert response.json()["status"] == "OK"
        assert response.json()["synthetic"]
        assert PRIVATE_CANARY not in response.text


def test_empty_filter_does_not_claim_business_health(fixture_api):
    result = fixture_api.get("/n8n/executions/failed?workflow_id=other").json()
    assert result["status"] == "OK"
    assert result["executions"] == []
    assert result["execution"] is None


def test_unavailable_fixture_record_is_inspection_failure(fixture_api):
    result = fixture_api.get("/n8n/executions/9999").json()
    assert result["status"] == "CHECK_FAILED"
    assert result["reason"] == "not_found"


@pytest.mark.parametrize(
    "path",
    [
        "/n8n/workflows?limit=0",
        "/n8n/workflows?limit=51",
        "/n8n/workflows?cursor=https://evil.example",
        "/n8n/executions/0",
        "/n8n/executions/arbitrary",
        "/n8n/executions/failed?workflow_id=..",
    ],
)
def test_invalid_api_input_rejected(fixture_api, path):
    assert fixture_api.get(path).status_code == 422


def test_no_write_routes(fixture_api):
    for method in ("post", "put", "patch", "delete"):
        assert getattr(fixture_api, method)("/n8n/workflows").status_code == 405
        assert getattr(fixture_api, method)("/n8n/executions/1001").status_code == 405
    assert fixture_api.post("/n8n/executions/1001/retry").status_code == 404


@pytest.mark.parametrize(
    ("mode", "reason"), [("disabled", "integration_disabled"), ("live", "missing_configuration")]
)
def test_credentials_do_not_block_backend_start(mode, reason):
    settings = Settings(
        _env_file=None, environment="test", n8n_mode=mode, n8n_base_url=None, n8n_api_key=None
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        result = client.get("/n8n/workflows").json()
        assert result["status"] == "CHECK_FAILED"
        assert result["reason"] == reason
        assert result["synthetic"] is False


def test_production_blocks_demo_and_inspection_routes():
    with pytest.raises(ValidationError, match="Synthetic n8n"):
        Settings(_env_file=None, environment="production", n8n_mode="fixture")
    with TestClient(
        create_app(Settings(_env_file=None, environment="production", n8n_mode="disabled"))
    ) as client:
        for path in (
            "/services/n8n",
            "/n8n/workflows",
            "/n8n/executions/failed",
            "/n8n/executions/1001",
        ):
            assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "value",
    [
        "http://n8n.example/api/v1",
        "https://127.0.0.1/api/v1",
        "https://n8n.local/api/v1",
        "https://n8n.example:8080/api/v1",
        "https://n8n.example/",
        "https://n8n.example/api/v2",
        "https://user:secret@n8n.example/api/v1",
        "https://n8n.example/api/v1?key=secret",
    ],
)
def test_configuration_rejects_unsafe_or_wrong_api_roots(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, n8n_base_url=value)


def test_configuration_normalizes_optional_values_and_masks_key():
    settings = Settings(
        _env_file=None, n8n_base_url="https://n8n.example/prefix/api/v1", n8n_api_key="private-key"
    )
    assert settings.n8n_base_url == "https://n8n.example/prefix/api/v1/"
    assert "private-key" not in repr(settings)
    empty = Settings(_env_file=None, n8n_base_url="", n8n_api_key="  ")
    assert empty.n8n_base_url is None
    assert empty.n8n_api_key is None
