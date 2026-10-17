"""Real built Next.js -> Uvicorn -> scratch SQLite/fixtures, with real Chromium."""

import json

from frontend_support import command, fixture_environment, frontend_server, seed
from playwright.sync_api import expect, sync_playwright
from smoke_support import ROOT, server


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def no_overflow(page):
    require(
        page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"),
        "Horizontal viewport overflow",
    )


def main():
    environment = fixture_environment()
    command(environment, "app.db.cli", "upgrade")
    logs, evidence = ROOT / "work/logs", ROOT / "work/evidence"
    logs.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            with server(environment, logs / "frontend-smoke-backend.log") as backend:
                identifiers = seed(backend, environment)
                with frontend_server(backend.base_url) as frontend:
                    snapshot = frontend.get("/api/dashboard")
                    snapshot.raise_for_status()
                    result = snapshot.json()
                    require(result["health"]["data"]["status"] == "ok", "Liveness missing")
                    require(len(result["incidents"]["data"]) == 1, "Incident missing")
                    require(result["actions"]["data"][0]["state"] == "PENDING", "Action missing")
                    require(
                        "SYNTHETIC_PRIVATE_DATA" not in snapshot.text, "Private fixture data leaked"
                    )
                    require(snapshot.headers["cache-control"] == "no-store", "Dashboard cached")
                    require(
                        frontend.get("/api/dashboard", headers={"Host": "evil.test"}).status_code
                        == 403,
                        "Remote host accepted",
                    )
                    require(
                        frontend.post(
                            "/api/investigations",
                            headers={"Origin": "https://evil.test"},
                            json={"question": "Why?"},
                        ).status_code
                        == 403,
                        "Cross-origin mutation accepted",
                    )
                    require(
                        frontend.post("/api/investigations", json={"question": "Why?"}).status_code
                        == 403,
                        "Originless mutation accepted",
                    )
                    for path in ("/api/actions", "/api/recovery", "/api/resolve"):
                        require(frontend.post(path).status_code == 404, "Unexpected write route")
                    page = browser.new_page(viewport={"width": 1536, "height": 1080})
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(str(frontend.base_url))
                    expect(page.get_by_role("heading", name="Reliability overview")).to_be_visible()
                    expect(page.get_by_text("One incident needs a closer look.")).to_be_visible()
                    no_overflow(page)
                    page.screenshot(
                        path=str(evidence / "phase-13-desktop.png"),
                        full_page=True,
                        animations="disabled",
                    )
                    page.get_by_role("button", name="Inspect latest incident").click()
                    dialog = page.get_by_role("dialog")
                    expect(dialog.get_by_text("Awaiting operator", exact=True)).to_be_visible()
                    expect(dialog.get_by_text("Unknown · unverified", exact=True)).to_be_visible()
                    dialog.get_by_role("button", name="Evidence").click()
                    expect(dialog.get_by_text("View sanitized evidence").first).to_be_visible()
                    dialog.get_by_text("View sanitized evidence").first.click()
                    expect(dialog.locator("pre").first).to_contain_text('"http_status": 401')
                    page.screenshot(
                        path=str(evidence / "phase-13-incident.png"),
                        full_page=True,
                        animations="disabled",
                    )
                    page.keyboard.press("Escape")
                    expect(dialog).to_have_count(0)
                    page.get_by_role("button", name="Use booking-confirmation question").click()
                    page.get_by_role("button", name="Investigate", exact=True).click()
                    expect(page.get_by_text("Scripted fixture", exact=True)).to_be_visible(
                        timeout=45_000
                    )
                    expect(page.get_by_text("Completed", exact=True)).to_be_visible()
                    expect(page.get_by_text("Cause unverified", exact=False)).to_be_visible()
                    page.get_by_label("Search records").fill("no-such-service")
                    expect(page.get_by_text("No matching observations")).to_be_visible()
                    page.get_by_label("Search records").fill("")
                    page.get_by_role("button", name="Non-synthetic", exact=True).click()
                    expect(page.get_by_text("No matching observations")).to_be_visible()
                    page.get_by_role("button", name="All sources", exact=True).click()
                    receipt = command(
                        environment,
                        "app.actions.cli",
                        "execute",
                        "--action-id",
                        identifiers["action_id"],
                        "--approve-retry-side-effects",
                    )
                    require(receipt["status"] == "ACCEPTED", "Fixture retry failed")
                    page.get_by_role("button", name="Refresh records").click()
                    page.get_by_role("button", name="Activity", exact=True).click()
                    expect(page.get_by_text("Retry accepted", exact=True)).to_be_visible()
                    incident = backend.get(
                        f"/history/incidents/{identifiers['incident_id']}"
                    ).json()
                    require(incident["status"] == "OPEN", "Accepted receipt closed incident")
                    proof = command(
                        environment,
                        "app.recovery.cli",
                        "verify",
                        "--action-id",
                        identifiers["action_id"],
                    )
                    require(proof["status"] == "VERIFIED", "Scoped proof failed")
                    page.get_by_role("button", name="Refresh records").click()
                    expect(page.get_by_text("Verified", exact=True)).to_be_visible()
                    expect(
                        page.get_by_text("Customer delivery and root cause remain unverified.")
                    ).to_be_visible()
                    page.get_by_role("button", name="Inspect proof").click()
                    expect(page.get_by_text("Required-node resolution", exact=True)).to_be_visible()
                    page.get_by_role("button", name="Close incident").click()
                    page.get_by_role("button", name="Overview", exact=True).click()
                    page.set_viewport_size({"width": 390, "height": 844})
                    no_overflow(page)
                    page.screenshot(
                        path=str(evidence / "phase-13-mobile.png"),
                        full_page=True,
                        animations="disabled",
                    )
                    page.get_by_role("button", name="Incidents", exact=True).click()
                    page.get_by_label("Incident status").select_option("RESOLVED")
                    expect(page.locator(".incident-row .status")).to_have_text("Resolved")
                    page.get_by_role("button", name="Connections", exact=True).click()
                    expect(
                        page.get_by_role("heading", name="Workspace capabilities")
                    ).to_be_visible()
                    no_overflow(page)
                    page.close()
            empty_environment = fixture_environment()
            empty_environment.update(
                INVESTIGATION_MODE="disabled",
                INCIDENTS_ENABLED="false",
                N8N_RETRY_MODE="disabled",
                N8N_RECOVERY_MODE="disabled",
            )
            command(empty_environment, "app.db.cli", "upgrade")
            with server(empty_environment, logs / "frontend-empty-backend.log") as backend:
                # The frontend stays up while this isolated backend becomes unavailable.
                with frontend_server(backend.base_url, name="frontend-empty") as frontend:
                    page = browser.new_page(viewport={"width": 1280, "height": 900})
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(str(frontend.base_url))
                    expect(page.get_by_text("Ready for your first signal.")).to_be_visible()
                    expect(
                        page.get_by_role("button", name="Investigate", exact=True)
                    ).to_be_disabled()
                    no_overflow(page)
                    page.close()
            disabled_environment = {**empty_environment, "STORAGE_MODE": "disabled"}
            with server(disabled_environment, logs / "frontend-disabled-backend.log") as backend:
                with frontend_server(backend.base_url, name="frontend-disabled") as frontend:
                    page = browser.new_page(viewport={"width": 1280, "height": 900})
                    page.goto(str(frontend.base_url))
                    expect(
                        page.get_by_text("Some history is unavailable.", exact=False)
                    ).to_be_visible()
                    expect(page.get_by_text("The evidence is incomplete.")).to_be_visible()
                    no_overflow(page)
                    page.close()
            with frontend_server("http://127.0.0.1:1", name="frontend-offline") as frontend:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.goto(str(frontend.base_url))
                expect(
                    page.get_by_text("Backend connection unavailable.", exact=False)
                ).to_be_visible()
                expect(page.get_by_text("The evidence is incomplete.")).to_be_visible()
                page.close()
            require(not errors, "Browser runtime errors occurred")
        finally:
            browser.close()
    result = {
        "result": "PASS",
        "built_nextjs_real_uvicorn_real_chromium": True,
        "scratch_sqlite": True,
        "desktop_mobile_no_horizontal_overflow": True,
        "investigation_validated_scripted_fixture": True,
        "incident_evidence_and_keyboard_dismissal": True,
        "source_search_and_status_filters": True,
        "pending_accepted_then_scoped_verified_resolution": True,
        "accepted_receipt_did_not_resolve": True,
        "empty_disabled_storage_and_offline_states": True,
        "same_origin_loopback_and_no_http_remediation": True,
        "browser_runtime_errors": len(errors),
        "live_provider_calls": False,
        "business_outcome_verified": False,
    }
    (evidence / "phase-13-frontend-smoke.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
