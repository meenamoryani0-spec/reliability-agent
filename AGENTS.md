# Project implementation instructions

- The user's continuation authorizes local completion work while Nebius access
  is pending. WEBSITE_MONITORING_ENABLED adds an opt-in single-process website
  timer, disabled by default; read docs/WEBSITE-SCHEDULE.md. Preserve explicit
  incident policy, saved-target validation, probe limits, graceful draining and
  truthful sleep/downtime gaps. Local verification does not activate deployed
  monitoring or establish always-on operation.

- The user's 19 October request authorizes repairing setup and project clarity.
  FREE-N8N-REPORTING.md documents an optional, disabled-by-default Error Trigger
  receiver. It accepts only two IDs through a separate ingest-only token, keeps
  source identity separate, and deduplicates immutable saved observations. It
  adds one bounded model read tool only when reporting is enabled. This is not
  API polling, node evidence, recovery proof or remediation. Creating a draft
  does not authorize silently replacing existing workflow error handlers.

- 19 October user-authorized operator setup adds migration `0006_operator_targets`,
  persistent operator-managed public website targets, and manual website/provider
  reads in the authenticated dashboard. Read docs/MONITORING-SETUP.md. Older
  references to head 0005 and pending frontend cloud deployment are historical.
  Keep model tools limited to registered IDs; target registration is operator-only.
  No scheduler, credential changes, paid plan or production remediation is implied.

Read README.md and docs/HANDOFF.md before extending the application.

- Keep all new project files, virtual environments, caches, and logs on D:.
- Build incrementally and run each component and its local tests before extending it.
- User clarification on 2026-10-10: API credentials must not block local development. Use mocks/local fixtures; defer real provider tests until credentials are supplied.
- Phases 1 and 3-13 are locally verified. Phase 14 now implements authenticated deployment preparation; read docs/PHASE-14.md, docs/DEPLOYMENT.md, docs/FRONTEND-REFINEMENT.md and docs/CURRENT-STATE.md. The original Phase 14 includes live cloud deployment, which remains pending hosting accounts/domains, Linux Docker execution and Supabase acceptance. Do not claim Phase 14 fully complete or begin Phase 15 automatically. Commit verified local preparation, then stop. Never push, provision paid resources, deploy or alter provider secrets without an actual configured destination and the applicable user authorization.
- Registry execution stays internal; GET /tools is an authenticated production catalog. Local mode has 13 bounded read tools; production excludes the synthetic browser fixture tool and has 12. Preserve strict schemas, byte/deadline limits, fixture flags, history failure separation and occupied slots until timed-out/cancelled adapter work finishes. No arbitrary shell/SQL/URL, registry execution endpoint or remediation tools.
- Investigation defaults to disabled. Fixture inference is explicitly scripted and requires n8n/infrastructure fixtures; no live website tools in this mode. Live inference is opt-in and sends the question/restricted evidence to Nebius. Keep 6-turn/8-tool/120-second limits, supported citations/conclusions, authenticated production access and cancellation draining. No model prose as verified cause or remediation. Phase 10 incident creation is a separate server policy, never a model-controlled write tool.
- Automatic incidents default off (INCIDENTS_ENABLED=false); production enablement requires configured authenticated access and migrated storage. Only persisted UNHEALTHY checks qualify. Preserve one unresolved incident per service/kind, unique observation links, source/synthetic separation and separate check/incident commits. Counts are observations, not affected bookings. Healthy checks alone cannot resolve incidents; Phase 12 requires validated recovery proof. Only validated, cited and individually supported hypotheses/recommendations can be stored as assessments against linked evidence. Root cause remains explicitly unknown; never turn a 401 into credential expiry. Migration head is 0005_verified_recovery. No background scheduler, automatic action retry or historical reconciliation exists.
- Retry defaults disabled (N8N_RETRY_MODE); enablement requires migrated storage, matching n8n mode and workflow allowlist. Preserve exact incident/check/source/execution binding, five-minute expiry, explicit per-action side-effects approval, fresh provider preflight, committed approval/dispatch intent before POST, and unique one-shot source/execution audit. No reset/retry of uncertain or consumed actions; no automatic resend after errors or restart. Keep the original workflow (loadWorkflow=false), no model/HTTP approval or execution route, production rejection and draining on cancellation. ACCEPTED is only a provider receipt; never resolve or claim recovery from it. Local operator approval is not authenticated production identity or proof of idempotence.
- Application storage is separate from monitored POSTGRES_* credentials. Run migrations explicitly; do not auto-migrate on startup or add arbitrary SQL/HTTP migration endpoints. Keep synthetic/live identities separate. The current schema requires a VERIFIED same-incident proof referencing a healthy check before resolution; downgrade refuses to discard recovery history.
- Do not claim real integrations or the complete application work until live provider and end-to-end validation pass.
- Follow the handoff's Python/FastAPI backend-first order; no empty future modules.
- Check current official provider documentation before implementing API adapters.
- Keep credentials in environment variables; never commit .env or print secrets.
- Separate read checks from write actions. No arbitrary shell or SQL tools for the model.
- Unknown/check-failed is different from unhealthy. Require evidence for root causes.
- Never resolve an incident without successful recovery verification.
- Run scripts/test.ps1 and a live HTTP smoke test for backend milestones.
- Commit verified stable milestones; report untested integrations accurately.
- Docker is optional until the backend host is chosen; it is not needed for Phase 1.

- Phase 12 recovery defaults disabled, uses only the local operator CLI and one bounded exact-execution GET. Preserve source/synthetic/mode/receipt/lineage binding, required-node policy, explicit successful attempt counts, completion node and freshness checks, separate check commit, atomic proof/resolution, additional-failure guard and per-service detection/closure lock. Resolution scope n8n_required_nodes is not customer delivery or global recovery; business outcome/root cause remain unverified. Historical proof reuse is explicit; original failure repolls reuse the closed incident, different failed executions may open a new one. No model/HTTP verification or resolve writes; production remains blocked. All live provider/recovery behavior remains unverified.
- SQLite migration batch rebuilds must use db.migrate.migration_transaction, verify all FKs before commit and restore enforcement. Never copy the destructive test fixture teardown into application code. The optional PostgreSQL -TemplateDir fallback copies only validated clean stopped project test clusters and uses a fresh scratch database/password; fresh initdb timed out in this session for an unestablished reason. Never point it at user/customer data.
- Frontend history collections are bounded to the latest 100 records; metrics describe that window. Preserve source/synthetic identity, stale evidence, unknown causes, disabled/offline/partial-history states and historical required-node proof scope. Refresh reads history only. The homepage is illustrative and makes no provider calls; the operational app is /dashboard. Local mode stays loopback-only. Production requires the single-operator signed secure session, fixed HTTPS backend and server bearer key, exact Host/Origin checks, no browser-to-backend CORS, server-only secrets, byte/schema/time limits and no-store data. Remediation stays in the CLI and production retry/recovery remain disabled. The synthetic preview uses only its own scratch database/fixture providers.

- Phase 14 supports one trusted operator/organization and one backend instance/worker. Session expiry is eight hours; logout clears only the current browser cookie. Rotating signing/operator keys revokes all sessions. Per-instance rate budgets are not distributed limits; public hosting needs edge limits and TLS. Never weaken PostgreSQL verify-full TLS; use STORAGE_SSL_CA_FILE for a validated mounted project CA if required. /ready verifies access and current schema, never migrates or checks monitored providers. Keep the remaining cloud/Docker/live-provider limitations explicit.
