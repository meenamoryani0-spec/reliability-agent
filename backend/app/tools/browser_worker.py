"""Real Chromium, fixed local responses, no external network continuation.

Runs in its own process to isolate Playwright's event loop from Windows Uvicorn.
Only bounded typed evidence is printed; never browser text or exception details.
"""

import json
import sys
import time

from playwright.sync_api import Error, Route, TimeoutError, expect, sync_playwright

from app.tools.browser_fixtures import API_URL, BOOKING_HTML, PAGE_URL
from app.tools.browser_models import FLOW_IDS, BrowserEvidence, BrowserFlowResult, FlowId
from app.tools.models import CheckStatus


def run_flow(flow_id: FlowId) -> BrowserFlowResult:
    started = time.monotonic()
    evidence = BrowserEvidence(reason="browser_unavailable")
    status = CheckStatus.CHECK_FAILED
    summary = "Synthetic browser check could not complete"

    def intercept(route: Route) -> None:
        request = route.request
        if request.url == PAGE_URL and request.method == "GET":
            route.fulfill(status=200, content_type="text/html", body=BOOKING_HTML)
        elif request.url == API_URL and request.method == "POST":
            failed = flow_id == "booking-crm-failure"
            evidence.booking_http_status = 502 if failed else 200
            route.fulfill(
                status=evidence.booking_http_status,
                content_type="application/json",
                body=json.dumps(
                    {"error": "fixture_crm_auth_rejected"} if failed else {"confirmed": True}
                ),
            )
        else:
            evidence.blocked_request_count = min(evidence.blocked_request_count + 1, 1000)
            route.abort("blockedbyclient")

    def count_console(message) -> None:
        if message.type == "error":
            evidence.console_error_count = min(evidence.console_error_count + 1, 1000)

    def count_page_error(_error) -> None:
        evidence.page_error_count = min(evidence.page_error_count + 1, 1000)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, timeout=10000)
            try:
                evidence.browser_version = browser.version
                context = browser.new_context(service_workers="block", accept_downloads=False)
                context.set_default_timeout(3000)
                context.set_default_navigation_timeout(5000)
                context.route("**/*", intercept)
                page = context.new_page()
                page.on("console", count_console)
                page.on("pageerror", count_page_error)
                evidence.stage = "navigation"
                response = page.goto(PAGE_URL, wait_until="domcontentloaded")
                evidence.navigation_http_status = response.status if response else None
                evidence.stage = "submit"
                page.get_by_label("Customer name", exact=True).fill("Synthetic customer")
                page.get_by_role("button", name="Book appointment", exact=True).click()
                evidence.stage = "verification"
                result = page.get_by_role("status")
                expect(result).to_have_text(
                    "Booking confirmed" if flow_id == "booking-healthy" else "Booking unavailable"
                )
                evidence.confirmation_visible = result.inner_text() == "Booking confirmed"
                evidence.failure_visible = result.inner_text() == "Booking unavailable"
                if evidence.blocked_request_count:
                    evidence.reason = "network_request_blocked"
                elif (
                    evidence.navigation_http_status == 200
                    and evidence.booking_http_status == 502
                    and evidence.failure_visible
                    and not evidence.confirmation_visible
                ):
                    status = CheckStatus.UNHEALTHY
                    evidence.reason = "fixture_crm_auth_rejected"
                    summary = (
                        "Synthetic booking failed after a simulated CRM authentication rejection"
                    )
                elif (
                    evidence.navigation_http_status == 200
                    and evidence.booking_http_status == 200
                    and evidence.confirmation_visible
                ):
                    if evidence.console_error_count or evidence.page_error_count:
                        status = CheckStatus.DEGRADED
                        evidence.reason = "frontend_errors"
                        summary = "Synthetic booking confirmed with frontend errors"
                    else:
                        status = CheckStatus.HEALTHY
                        evidence.reason = "confirmation_verified"
                        summary = "Synthetic booking submission and visible confirmation verified"
                else:
                    evidence.reason = "confirmation_not_verified"
            finally:
                browser.close()
    except TimeoutError:
        status = CheckStatus.CHECK_FAILED
        summary = "Synthetic browser check could not complete"
        evidence.reason = "browser_timeout"
    except Error:
        status = CheckStatus.CHECK_FAILED
        summary = "Synthetic browser check could not complete"
        evidence.reason = (
            "browser_unavailable" if evidence.stage == "launch" else "browser_execution_failed"
        )
    except AssertionError:
        status = CheckStatus.CHECK_FAILED
        summary = "Synthetic browser check could not verify the expected UI outcome"
        evidence.reason = (
            "network_request_blocked"
            if evidence.blocked_request_count
            else "confirmation_not_verified"
        )
    return BrowserFlowResult(
        component=flow_id,
        status=status,
        severity=(
            "none"
            if status == CheckStatus.HEALTHY
            else "warning"
            if status == CheckStatus.DEGRADED
            else "error"
        ),
        summary=summary,
        evidence=evidence,
        latency_ms=round((time.monotonic() - started) * 1000, 2),
    )


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in FLOW_IDS:
        raise SystemExit(2)
    print(run_flow(sys.argv[1]).model_dump_json())


if __name__ == "__main__":
    main()
