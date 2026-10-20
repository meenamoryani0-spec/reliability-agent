import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "deployment_probe", Path(__file__).resolve().parents[2] / "scripts/deployment_probe.py"
)
probe_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_module)


def test_cold_backend_loading_is_retried_without_claiming_readiness():
    reader = Mock(
        side_effect=[
            {"passed": False, "reason": "unexpected_content_type"},
            {"passed": True, "reason": "expected_status"},
            {"passed": True, "reason": "expected_status"},
        ]
    )
    pause = Mock()
    result = probe_module.check_deployment(read=reader, pause=pause)
    assert result["result"] == "PASS"
    assert result["checks"]["backend"]["attempts"] == 2
    assert result["business_outcome_verified"] is False
    pause.assert_called_once_with(10)


def test_failed_backend_is_bounded_and_frontend_is_still_checked():
    reader = Mock(return_value={"passed": False, "reason": "request_failed"})
    pause = Mock()
    result = probe_module.check_deployment(read=reader, pause=pause)
    assert result["result"] == "NOT_READY"
    assert reader.call_count == 4 and pause.call_count == 2
    assert result["checks"]["backend"]["attempts"] == 3
    assert result["checks"]["frontend"]["attempts"] == 1


@pytest.mark.parametrize("status", [401, 403])
def test_auth_rejection_is_not_retried_or_diagnosed_as_expiry(status):
    reader = Mock(return_value={"passed": False, "reason": "http_error", "http_status": status})
    pause = Mock()
    result = probe_module.check_deployment(read=reader, pause=pause)
    assert result["result"] == "NOT_READY" and reader.call_count == 2
    pause.assert_not_called()


@pytest.mark.parametrize(
    "content_type,body,passed,reason",
    [
        ("text/html", b"<html>Application loading</html>", False, "unexpected_content_type"),
        ("application/json", b'{"status":"ready"}', True, "expected_status"),
        ("application/json", b'{"status":"not_ready"}', False, "not_ready"),
        ("application/json", b"[]", False, "not_ready"),
        ("application/json", b"invalid", False, "invalid_json"),
        ("application/json", b"x" * 2049, False, "response_too_large"),
    ],
)
def test_only_bounded_expected_json_counts_as_ready(
    monkeypatch, content_type, body, passed, reason
):
    response = Mock(status=200)
    response.headers.get_content_type.return_value = content_type
    response.read.return_value = body
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    monkeypatch.setattr(probe_module, "build_opener", Mock(return_value=opener))
    result = probe_module.probe("https://fixed.example/ready", "ready")
    assert result == {"passed": passed, "reason": reason}


def test_redirects_are_rejected():
    assert probe_module.NoRedirect().redirect_request(None) is None
