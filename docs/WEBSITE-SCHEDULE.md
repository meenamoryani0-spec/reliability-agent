# Automatic website checks

An opt-in timer runs the existing registered website HTTP, DNS and TLS probes and
saves their observations through the existing history/incident policy. It adds
no provider credentials, model write tools, migrations, or remote activation API.

## Configuration

```dotenv
WEBSITE_MONITORING_ENABLED=false
WEBSITE_MONITORING_INTERVAL_SECONDS=300
```

Disabled is the default. Enabling requires application storage and operations
access; scripted investigation mode is rejected. Production still requires its
existing authenticated access and PostgreSQL configuration. Migrate storage
explicitly before enabling; the timer never migrates it.

The interval is 60–86400 seconds, with a default of 300. A scan starts when the
application starts, then the timer waits the configured interval after each scan
finishes. A scan's duration is additional to that interval. All currently
registered targets, up to the existing limit of 25, are reloaded for each scan.
Probes run sequentially with the existing network/SSRF and timeout protections.
The automatic scan shares the operator batch-check slot; a busy slot skips that
scan rather than overlapping or queuing a backlog. Independent bounded agent
and single-check routes retain their existing concurrency policies.

When history cannot verify readiness, the scan makes no probe requests. Failed
cycles retain a sanitized status and wait before the next attempt. Shutdown
signals the timer to stop, finishes its current target batch and history writes,
then closes the target and storage services.

## Incidents and recovery

`INCIDENTS_ENABLED` remains independent and off by default. When enabled, saved
UNHEALTHY observations use the existing incident deduplication policy. Healthy
observations never automatically resolve an incident. There is no automatic
retry, repair, AI diagnosis or customer-flow test in this timer.

## What the dashboard means

Authenticated `GET /monitoring` exposes `automatic_monitoring` and
`website_schedule`. The latter includes the interval, current timer state, last
scan timestamps, sanitized outcome, saved-check count and cycle count. Timer
state/counts reset with the backend process; check history persists separately.
A completed scan means its observations were saved, not that the website is
healthy. Read Checks history for actual observation status and freshness.

The frontend accepts older backends without timer metadata and shows disabled,
unknown, waiting, checking and failed/partial outcomes without claiming health.
Refresh records reloads history. With automatic checks enabled, Reload monitoring
status fetches the separate monitoring settings/activity snapshot; reopening
Connections or reloading the page also fetches that snapshot.

## Runtime limits

This is a timer inside the single backend process. It cannot run while that
process is sleeping, stopped or unavailable. Missed scans are not replayed.
There is no distributed scheduler or durable job queue. It does not establish
always-on monitoring on a free hosting tier.

The separate `Monitor deployed application` GitHub Actions workflow probes the
frontend's public liveness endpoint and the backend's public storage-readiness
endpoint approximately every five minutes. Incoming readiness requests can wake
the free backend. It uses no credentials, changes no application data, rejects
redirects/HTML loading screens, and makes at most three backend read attempts.
The workflow has a four-minute job limit. Job failures are visible in Actions;
notification delivery depends on the operator's GitHub notification settings.

This external probe is independent of the in-process website timer. It verifies
application availability, not website business flows, n8n execution success or
customer delivery. GitHub schedules can be delayed or dropped and public-repo
schedules can be disabled after 60 days without repository activity. It is
best-effort coverage, not a guaranteed interval or a service-level agreement.
See [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The timer still requires explicit deployment/configuration. A passing local
or CI run does not establish that it has been activated in production.

## Validation commands

```powershell
.\scripts\test.ps1
. .\scripts\environment.ps1
& $ProjectPython scripts\website_schedule_smoke.py
.\scripts\smoke.ps1
.\scripts\frontend-check.ps1
.\scripts\frontend-smoke.ps1
```

The scheduler smoke starts actual loopback Uvicorn/HTTP, explicitly migrates a
new scratch SQLite database, and verifies automatic history/incident capture.
Website probe responses in that smoke are controlled fixtures. It makes no
live website/provider/model calls and is not proof of a customer's outage.
