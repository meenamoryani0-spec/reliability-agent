from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_reports_liveness(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok", "service": "reliability-agent-backend"}


def test_health_is_read_only(client):
    assert client.post("/health").status_code == 405


def test_unknown_route(client):
    assert client.get("/diagnose").status_code == 404


def test_health_is_documented(client):
    schema = client.get("/openapi.json").json()
    assert "/health" in schema["paths"]
    assert client.get("/docs").status_code == 200


def test_production_disables_docs_but_preserves_health():
    settings = Settings(_env_file=None, environment="production")
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health").status_code == 200
