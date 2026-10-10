import asyncio
import subprocess
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tools.browser import BrowserChecker, failed_result, stop_worker
from app.tools.browser_models import FLOW_IDS


@pytest.mark.parametrize("flow_id", FLOW_IDS)
def test_api_dispatches_only_registered_flows(flow_id):
    checker = Mock()

    async def check(value):
        assert value == flow_id
        return failed_result(value, "browser_unavailable")

    checker.check = check
    with TestClient(
        create_app(Settings(_env_file=None, environment="test"), browser_checker=checker)
    ) as client:
        data = client.post(f"/checks/browser-flows/{flow_id}").json()
    assert data["check_type"] == "browser"
    assert data["healthy"] is None
    assert data["evidence"]["synthetic"] is True


def test_registry_and_unknown_flow(client):
    assert client.get("/services/browser-flows").json() == [
        {"id": flow_id, "synthetic": True} for flow_id in FLOW_IDS
    ]
    assert client.post("/checks/browser-flows/unconfigured").status_code == 404
    assert client.get("/checks/browser-flows/booking-healthy").status_code == 405
    assert client.post("/checks/websites/demo?kind=browser").status_code == 422


def test_production_disables_browser_operations():
    checker = Mock()
    with TestClient(
        create_app(Settings(_env_file=None, environment="production"), browser_checker=checker)
    ) as client:
        assert client.get("/services/browser-flows").status_code == 404
        for flow_id in FLOW_IDS:
            assert client.post(f"/checks/browser-flows/{flow_id}").status_code == 404
    checker.check.assert_not_called()


def test_arbitrary_flow_rejected_before_worker(monkeypatch):
    popen = Mock()
    monkeypatch.setattr("app.tools.browser.subprocess.Popen", popen)
    with pytest.raises(ValueError, match="not configured"):
        asyncio.run(BrowserChecker().check("https://127.0.0.1"))
    popen.assert_not_called()


def test_busy_is_check_failed_without_launch(monkeypatch):
    popen = Mock()
    monkeypatch.setattr("app.tools.browser.subprocess.Popen", popen)
    checker = BrowserChecker()
    checker._lock.acquire()
    try:
        result = asyncio.run(checker.check("booking-healthy"))
    finally:
        checker._lock.release()
    assert result.evidence.reason == "browser_busy"
    assert result.healthy is None
    popen.assert_not_called()


@pytest.mark.parametrize("output", ["bad json SECRET", "{}", "x" * 16385])
def test_invalid_worker_output_is_sanitized(monkeypatch, output):
    process = Mock(returncode=0)
    process.communicate.return_value = (output, None)
    process.poll.return_value = 0
    monkeypatch.setattr("app.tools.browser.subprocess.Popen", Mock(return_value=process))
    result = asyncio.run(BrowserChecker().check("booking-healthy"))
    assert result.evidence.reason == "browser_worker_invalid_output"
    assert result.healthy is None
    assert "SECRET" not in result.model_dump_json()


def test_worker_identity_is_checked(monkeypatch):
    process = Mock(returncode=0)
    process.communicate.return_value = (
        failed_result("booking-crm-failure", "browser_timeout").model_dump_json(),
        None,
    )
    process.poll.return_value = 0
    monkeypatch.setattr("app.tools.browser.subprocess.Popen", Mock(return_value=process))
    result = asyncio.run(BrowserChecker().check("booking-healthy"))
    assert result.evidence.reason == "browser_worker_invalid_output"


def test_timeout_cleans_worker_tree_and_releases_slot(monkeypatch):
    process = Mock(pid=1234)
    process.communicate.side_effect = subprocess.TimeoutExpired("worker", 30)
    process.poll.return_value = None
    monkeypatch.setattr("app.tools.browser.subprocess.Popen", Mock(return_value=process))
    cleanup = Mock()
    monkeypatch.setattr("app.tools.browser.stop_worker", cleanup)
    checker = BrowserChecker()
    result = asyncio.run(checker.check("booking-healthy"))
    assert result.evidence.reason == "browser_timeout"
    assert result.healthy is None
    cleanup.assert_called_once_with(process)
    assert checker._lock.acquire(blocking=False)
    checker._lock.release()


def test_worker_environment_excludes_provider_secrets(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "SECRET")
    monkeypatch.setenv("HTTPS_PROXY", "http://SECRET")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "C:\\wrong")
    process = Mock(returncode=1)
    process.communicate.return_value = ("SECRET", None)
    process.poll.return_value = 1
    popen = Mock(return_value=process)
    monkeypatch.setattr("app.tools.browser.subprocess.Popen", popen)
    result = asyncio.run(BrowserChecker().check("booking-healthy"))
    environment = popen.call_args.kwargs["env"]
    assert "NEBIUS_API_KEY" not in environment
    assert "HTTPS_PROXY" not in environment
    assert environment["PLAYWRIGHT_BROWSERS_PATH"].endswith("work\\browsers")
    assert "SECRET" not in result.model_dump_json()
    assert result.evidence.reason == "browser_worker_failed"


def test_worker_spawn_failure_does_not_claim_service_broken(monkeypatch):
    monkeypatch.setattr("app.tools.browser.subprocess.Popen", Mock(side_effect=OSError("SECRET")))
    result = asyncio.run(BrowserChecker().check("booking-healthy"))
    assert result.healthy is None
    assert "SECRET" not in result.model_dump_json()


def test_windows_tree_cleanup_falls_back_if_taskkill_fails(monkeypatch):
    monkeypatch.setattr("app.tools.browser.sys.platform", "win32")
    monkeypatch.setattr("app.tools.browser.subprocess.run", Mock(side_effect=OSError))
    process = Mock(pid=1234)
    process.poll.return_value = None
    stop_worker(process)
    process.kill.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)
