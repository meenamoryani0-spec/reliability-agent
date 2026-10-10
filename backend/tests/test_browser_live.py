"""Require installed Chromium; these tests never silently skip browser execution."""

import asyncio

import pytest

from app.tools.browser import BrowserChecker
from app.tools.browser_fixtures import BOOKING_HTML
from app.tools.browser_worker import run_flow


@pytest.mark.parametrize(
    ("flow_id", "status", "booking_status", "confirmed"),
    [
        ("booking-healthy", "HEALTHY", 200, True),
        ("booking-crm-failure", "UNHEALTHY", 502, False),
    ],
)
def test_real_browser_submits_and_verifies(flow_id, status, booking_status, confirmed):
    result = asyncio.run(BrowserChecker().check(flow_id))
    assert result.status == status, result.model_dump_json()
    assert result.evidence.navigation_http_status == 200
    assert result.evidence.booking_http_status == booking_status
    assert result.evidence.confirmation_visible is confirmed
    assert result.evidence.failure_visible is not confirmed
    assert result.evidence.blocked_request_count == 0
    assert result.evidence.browser_version
    if not confirmed:
        assert result.evidence.console_error_count >= 1
        assert result.evidence.reason == "fixture_crm_auth_rejected"


def test_console_and_page_errors_are_collected_without_raw_text(monkeypatch):
    monkeypatch.setattr(
        "app.tools.browser_worker.BOOKING_HTML",
        BOOKING_HTML.replace(
            "<script>",
            "<script>console.error('SECRET'); setTimeout(() => {throw Error('SECRET')}, 0);",
        ),
    )
    result = run_flow("booking-healthy")
    assert result.status == "DEGRADED"
    assert result.evidence.console_error_count >= 1
    assert result.evidence.page_error_count >= 1
    assert result.evidence.confirmation_visible
    assert "SECRET" not in result.model_dump_json()


def test_browser_blocks_nonfixture_destinations(monkeypatch):
    monkeypatch.setattr(
        "app.tools.browser_worker.BOOKING_HTML",
        BOOKING_HTML.replace(
            "const response = await fetch('/api/bookings',",
            "const response = await fetch('http://127.0.0.1:9/private',",
        ),
    )
    result = run_flow("booking-crm-failure")
    assert result.status == "CHECK_FAILED"
    assert result.healthy is None
    assert result.evidence.blocked_request_count == 1
    assert result.evidence.reason == "network_request_blocked"
    assert result.evidence.booking_http_status is None


def test_missing_chromium_reports_check_failed(monkeypatch, tmp_path):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "missing-browser"))
    result = run_flow("booking-healthy")
    assert result.status == "CHECK_FAILED"
    assert result.evidence.reason == "browser_unavailable"
    assert result.healthy is None


def test_success_http_status_without_ui_confirmation_is_not_healthy(monkeypatch):
    monkeypatch.setattr(
        "app.tools.browser_worker.BOOKING_HTML",
        BOOKING_HTML.replace(
            "result.textContent = 'Booking confirmed';", "result.textContent = '';"
        ),
    )
    result = run_flow("booking-healthy")
    assert result.status == "CHECK_FAILED"
    assert result.evidence.navigation_http_status == 200
    assert result.evidence.booking_http_status == 200
    assert not result.evidence.confirmation_visible
    assert result.evidence.reason == "confirmation_not_verified"
