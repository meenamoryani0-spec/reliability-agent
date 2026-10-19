# Operator website setup and manual provider checks

19 October 2026. This extends the deployed single-operator release without enabling
background polling, paid providers, remediation, or synthetic production modes.

The dashboard now accepts a public website URL, saves an immutable target, and
offers a separate Run checks action. That action performs HTTP, DNS, and TLS reads
and reports each observation separately from its persistence outcome. Refresh
records still only reloads history. No form or booking is submitted.

Targets persist in the private application schema through migration
`0006_operator_targets`. They are separate from observations, limited to 25
including environment-configured targets, and reused when the same URL is saved
again. Registration performs no network or model request. Existing URL parsing,
public destination/DNS/IP pinning, redirect and certificate policies apply to the
subsequent check. Only authenticated operators can register targets; the model's
tools still accept registered IDs, never arbitrary URLs. Target creation is not a
model tool. No delete or target-reassignment endpoint is introduced.

The website-check group has one slot per supported backend worker. A disconnected
caller does not release its slot while adapter/history work is still running.
Shutdown drains that work before disposing storage. The new frontend handler
requires an authenticated session and matching JSON Origin for all operations,
has bounded input/output and fixed backend paths, and never exposes service keys.

Connections now offers explicit n8n workflow/error lists and execution evidence,
plus the five existing infrastructure checks. Disabled or unconfigured connections
are shown as Needs connection. These operations reuse the existing bounded,
sanitized read adapters. Provider credentials remain in backend environment
settings. Provider connectivity, customer delivery, and causes are not inferred
from configuration or a successful list request.

n8n Cloud's current free trial does not provide its public API. The supplied
instance displayed a trial banner. Do not upgrade it automatically or use internal
editor endpoints as an API workaround. An API-enabled account or separately chosen
self-hosted instance is needed for live n8n inspection. Official reference:
https://support.n8n.io/article/can-i-have-api-access-while-im-on-a-trial

## Verified local checks

- Full backend suite with SQLite and isolated real PostgreSQL: 1,002 passed,
  zero skips; Ruff lint and format passed.
- Frontend: 29 tests, ESLint, TypeScript, production webpack build passed.
- Real built Next.js/Uvicorn/Chromium smoke passed with zero browser runtime
  errors, desktop/mobile layout, persistent website registration, fixture n8n
  workflow and execution inspection, and existing investigation/action/proof flows.
- Separate actual backend HTTP smoke passed.
- The browser smoke used scratch storage and synthetic providers; it did not
  establish a live n8n or AI connection.

## Rollout

Apply the additive migration explicitly under the existing migration owner. Grant
the restricted runtime role SELECT and INSERT on `reliability.website_targets`.
Do not change existing roles, passwords, .env files, table data, or proof rules.
The schema revision is checked before migration and table creation/version update
must commit in one transaction. Deploy the matching backend and frontend commits
and verify readiness, login, target persistence and a real operator-triggered check.

The Supabase rollout additionally enables RLS on this new table, with SELECT and
INSERT policies only for the existing restricted runtime role. No public Data API
access or provider credential permissions were added. Actual hdworks.tech HTTP,
DNS and TLS observations were healthy and persisted; deployed auth/storage smoke
passed. n8n/AI integrations remain disabled and unverified.

The older backend expects revision 0005, so coordinate the migration with the new
rollout. Do not downgrade or discard targets for rollback. The migration refuses
downgrade once saved targets exist. Continuous monitoring and live AI/provider
acceptance remain separate work.
# Additional free n8n reporting path

Read [FREE-N8N-REPORTING.md](FREE-N8N-REPORTING.md) for the optional Error Trigger
receiver. It is disabled until privately configured and validated. Public API
controls and reported-failure notifications have different coverage.
