import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings
from app.db.database import create_storage_engine
from app.db.migrate import upgrade
from app.main import create_app


def local_config(tmp_path, **kwargs):
    return Settings(
        _env_file=None,
        storage_mode="local",
        infrastructure_mode="fixture",
        n8n_mode="fixture",
        storage_sqlite_file=str((tmp_path / "api.sqlite3").relative_to(PROJECT_ROOT)),
        **kwargs,
    )


def test_check_history_survives_application_restart(tmp_path):
    config = local_config(tmp_path)
    engine = create_storage_engine(config)
    upgrade(engine)
    engine.dispose()
    with TestClient(create_app(config)) as client:
        result = client.post("/checks/infrastructure/vercel-deployment")
        assert result.status_code == 200 and result.headers["x-history-status"] == "saved"
        identifier = result.headers["x-check-id"]
        assert client.get("/storage").json()["state"] == "ready"
        assert client.get("/history/checks").json()[0]["id"] == identifier
        assert client.get("/history/incidents").json() == []
        assert client.get("/history/services").json()[0]["synthetic"] is True
    with TestClient(create_app(config)) as client:
        assert client.get("/history/checks/" + identifier).json()["status"] == "UNHEALTHY"
        assert client.get("/history/checks/" + str(uuid4())).status_code == 404


def test_n8n_execution_health_is_stored_but_lists_are_not(tmp_path):
    config = local_config(tmp_path)
    engine = create_storage_engine(config)
    upgrade(engine)
    engine.dispose()
    with TestClient(create_app(config)) as client:
        client.get("/n8n/workflows")
        assert client.get("/history/checks").json() == []
        for execution in ("1001", "1002"):
            response = client.get("/n8n/executions/" + execution)
            assert response.headers["x-history-status"] == "saved"
        history = client.get("/history/checks").json()
        assert {row["status"] for row in history} == {"HEALTHY", "UNHEALTHY"}
        assert len(client.get("/history/services").json()) == 1


def test_changed_postgres_port_has_a_distinct_service_identity(tmp_path):
    from unittest.mock import AsyncMock

    from app.tools.infrastructure_models import InfrastructureResult

    path = str((tmp_path / "ports.sqlite3").relative_to(PROJECT_ROOT))
    for port in (5432, 6543):
        config = Settings(
            _env_file=None,
            storage_mode="local",
            storage_sqlite_file=path,
            infrastructure_mode="live",
            postgres_host="db.example.com",
            postgres_port=port,
            postgres_dbname="postgres",
            postgres_user="probe",
        )
        engine = create_storage_engine(config)
        upgrade(engine)
        engine.dispose()
        adapter = AsyncMock()
        adapter.check.return_value = InfrastructureResult(
            component="postgres",
            check_type="connectivity",
            status="UNKNOWN",
            summary="No external database is contacted in this test",
        )
        with TestClient(create_app(config, infrastructure_service=adapter)) as client:
            assert (
                client.post("/checks/infrastructure/postgres").headers["x-history-status"]
                == "saved"
            )
            assert len(client.get("/history/services").json()) == (1 if port == 5432 else 2)


def test_missing_migration_preserves_check_result_and_reports_failed_save(tmp_path):
    config = local_config(tmp_path)
    with TestClient(create_app(config)) as client:
        result = client.post("/checks/infrastructure/vercel-deployment")
        assert (
            result.json()["status"] == "UNHEALTHY"
            and result.headers["x-history-status"] == "unavailable"
        )
        assert "x-check-id" not in result.headers
        assert client.get("/health").status_code == 200
        assert client.get("/storage").json()["state"] == "migration_required"
        assert client.get("/history/checks").status_code == 503


def test_storage_disabled_is_explicit(client):
    assert client.get("/storage").json()["state"] == "disabled"
    assert client.get("/history/checks").status_code == 503
    assert (
        client.post("/checks/infrastructure/vercel-deployment").headers["x-history-status"]
        == "disabled"
    )


@pytest.mark.parametrize(
    "path", ["/storage", "/history/services", "/history/checks", "/history/incidents"]
)
def test_history_routes_are_disabled_in_production(path):
    with TestClient(create_app(Settings(_env_file=None, environment="production"))) as client:
        assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "offset=-1", "offset=10001", "status=OK", "service_id=bad"]
)
def test_history_query_bounds(client, query):
    assert client.get("/history/checks?" + query).status_code == 422


def test_no_public_incident_write_resolution_or_sql_endpoint(client):
    assert client.post("/history/incidents", json={"status": "RESOLVED"}).status_code == 405
    assert client.delete("/history/checks").status_code == 405
    assert client.post("/storage/migrate").status_code == 404


@pytest.mark.parametrize(
    "kwargs",
    [
        {"storage_sqlite_file": "../escape.sqlite3"},
        {"storage_sqlite_file": "C:/outside.sqlite3"},
        {"storage_sqlite_file": "work/history.txt"},
        {"storage_mode": "postgresql"},
        {"storage_mode": "postgresql", "storage_database_url": "not-a-url"},
        {"storage_mode": "postgresql", "storage_database_url": "sqlite:///x"},
        {
            "storage_mode": "postgresql",
            "storage_database_url": "postgresql+psycopg://u:p@localhost/x",
        },
        {
            "storage_mode": "postgresql",
            "storage_database_url": "postgresql+psycopg://u:p@db.example/x?sslmode=disable",
        },
        {
            "storage_mode": "postgresql",
            "storage_database_url": "postgresql+psycopg://u:p@db.example/postgres%3A%2F%2Fevil",
        },
        {"storage_mode": "local", "environment": "production"},
        {"storage_allow_loopback": True, "environment": "production"},
    ],
)
def test_unsafe_storage_configuration_is_rejected(kwargs):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **kwargs)
    assert "u:p@" not in str(error.value)


def test_disabled_storage_does_not_require_any_credentials():
    from app.db.repository import StorageError
    from app.db.service import HistoryService

    history = HistoryService(Settings(_env_file=None))
    assert history.describe()["state"] == "disabled"
    with pytest.raises(StorageError, match="storage_disabled"):
        asyncio.run(history.read("services"))
