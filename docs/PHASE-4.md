# Phase 4 — Playwright synthetic booking verification

Implemented and verified on 10 October 2026. Scope stops at this phase.

## Implemented behavior

- Real headless Chromium launched through Playwright Python in an isolated worker.
- Navigation to a fixed synthetic booking page, form fill, submit, and UI assertion.
- Two fixed flow IDs: `booking-healthy` and `booking-crm-failure`.
- FastAPI registry and check endpoints, disabled in production.
- Structured browser evidence using the existing website result/status semantics.
- Console error and uncaught page error counts; raw browser text is discarded.
- Fresh browser context for each check, bounded steps, one active worker per process.
- A 30-second worker deadline and process-tree cleanup on timeout.
- Provider secrets/proxy settings excluded from the worker environment.
- Browser binaries, profiles, temporary files, caches, and evidence remain on D:.

The browser is real; the website and booking API are locally fulfilled fixtures.
The failure fixture returns a simulated CRM authentication rejection as HTTP 502.
This does not establish a real CRM root cause, call n8n, or create a real booking.

Every routed request except the exact fixture page GET and booking POST is aborted.
Service workers and downloads are disabled. The API accepts fixed flow IDs only.
This is not a network sandbox for arbitrary customer pages. A customer adapter
will need a separate destination policy, DNS/IP enforcement, permitted actions,
and approved test data before it can interact with an external website.

## Verification evidence

The full suite passed **158 tests**: the previous 138 plus 14 browser/API tests
and six tests that invoke actual Chromium. Real browser tests cover:

1. Successful booking POST and visible confirmation.
2. Intentional booking failure, visible failure, absent confirmation, console errors.
3. Console and uncaught page errors without retaining raw sensitive messages.
4. An attempted nonfixture loopback request being aborted and classified CHECK_FAILED.
5. Missing browser binaries classified CHECK_FAILED with `healthy: null`.
6. Both page/API returning HTTP 200 without visible confirmation remaining CHECK_FAILED.

Worker tests additionally cover busy handling, timeout cleanup, sanitized invalid
output, rejected arbitrary flow identifiers, subprocess errors, mismatched result
identity, secret/proxy exclusion, and production rejection before browser execution.

Ruff lint and formatting checks passed. `pip check` found no broken requirements.
Runtime and development locks retain hashes, adding Playwright 1.63.0, greenlet
3.5.6, and pyee 13.0.1 while retaining the previous dependency versions.

`scripts/browser-smoke.ps1` launched a real Uvicorn process, verified health/docs
and the website API regressions, then called both browser flow endpoints over HTTP.
It returned PASS and stopped the server in cleanup. Its observations at about
22:05 IST (16:35 UTC) on 10 October 2026 were:

| Evidence | Healthy fixture | Failure fixture |
| --- | --- | --- |
| Result | HEALTHY | UNHEALTHY |
| Browser | Chromium 153.0.8010.12 | Chromium 153.0.8010.12 |
| Page HTTP status | 200 | 200 |
| Booking API status | 200 | 502 |
| Confirmation visible | Yes | No |
| Failure visible | No | Yes |
| Console errors | 0 | 2 |
| Uncaught page errors | 0 | 0 |
| Blocked requests | 0 | 0 |

These are individual synthetic observations, not continuous monitoring.
Sanitized observations are saved to ignored `work/evidence/browser-smoke.json`.

## Installation issue and resolution

The normal Playwright installer downloaded Chromium but failed to extract it:
Node `fs.promises.realpath` returned EPERM for the browser extraction directory.
Explicit permission for that directory did not resolve this environment-specific
failure. The host reports Windows 11; the user profile name does not identify OS version.

The working fallback was:

```powershell
.\scripts\browser-install.ps1 -UseArchiveFallback
```

It reads the exact archive URLs and install destinations from the installed
Playwright CLI's `--dry-run`, downloads from the official CDN (including its
Chrome-for-Testing storage redirect), validates extraction paths and size bounds,
and extracts to the expected project-local D: directory. One transient FFmpeg
download disconnect succeeded on a manual rerun; completed archives are reused.
It also installed the matching FFmpeg and Winldd assets. No SDK source, OS
permission policy, or browser launch security settings were modified.
The fallback targets the three Windows assets reported by this pinned SDK;
the standard installer remains the default for other environments.

## Run commands

From the repository root, after initial dependency setup:

```powershell
.\scripts\browser-install.ps1
# If Node extraction fails with EPERM in this environment:
.\scripts\browser-install.ps1 -UseArchiveFallback
.\scripts\test.ps1
.\scripts\browser-smoke.ps1
```

## Limits and next milestone

Only synthetic booking flows are implemented. No customer website business
flow, n8n adapter, infrastructure adapter, database, agent loop, incident,
remediation, recovery orchestration, frontend, or deployment is implemented.
Real Nebius connectivity remains unverified and requires a key later.
No API credentials were needed for this milestone.

Stop here. The next milestone is Phase 5, read-only n8n integration with
mock/local execution evidence and current official API documentation.

## Official references checked

- [Playwright Python installation](https://playwright.dev/python/docs/intro)
- [Browser binaries, headless shell, custom install paths](https://playwright.dev/python/docs/browsers)
- [Network interception and locally fulfilled responses](https://playwright.dev/python/docs/network)
- [Route fulfill/abort API](https://playwright.dev/python/docs/api/class-route)
- [Page navigation and events](https://playwright.dev/python/docs/api/class-page)
- [Browser contexts and service worker blocking](https://playwright.dev/python/docs/api/class-browsercontext)

Also inspected the pinned SDK's local browser registry/CLI implementation for
its asset revisions, URLs, installation marker, and Windows extraction failure.
