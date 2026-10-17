# Project implementation instructions

Read README.md and docs/HANDOFF.md before extending the application.

- Keep all new project files, virtual environments, caches, and logs on D:.
- Build incrementally and run each component and its local tests before extending it.
- User clarification on 2026-10-10: API credentials must not block local development. Use mocks/local fixtures; defer real provider tests until credentials are supplied.
- Phases 1 and 3–10 are locally verified. Phase 10 adds opt-in automatic incidents from persisted UNHEALTHY checks, evidence links, database-enforced deduplication and supported assessment/recommendation persistence. Final regression: 720 passed, no skips, including SQLite, isolated PostgreSQL and real Chromium; lint/format/pip and actual Uvicorn restart smoke pass. Live providers and Nemotron/tool calling remain unverified. Next: Phase 11 — first approved write. Read docs/PHASE-10.md and docs/CURRENT-STATE.md.
- Registry execution stays internal; GET /tools is a local catalog only. Preserve strict schemas, byte/deadline limits, fixture flags, history failure separation and occupied slots until timed-out/cancelled adapter work finishes. No production registry access before deployment controls; no arbitrary shell/SQL/URL or remediation tools.
- Investigation defaults to disabled. Fixture inference is explicitly scripted and requires n8n/infrastructure fixtures; no live website tools in this mode. Live inference is opt-in and sends the question/restricted evidence to Nebius. Keep 6-turn/8-tool/120-second limits, supported citations/conclusions, production rejection and cancellation draining. No model prose as verified cause or remediation. Phase 10 incident creation is a separate server policy, never a model-controlled write tool.
- Automatic incidents default off (INCIDENTS_ENABLED=false); production enablement is rejected pending controls. Only persisted UNHEALTHY checks qualify. Preserve one unresolved incident per service/kind, unique observation links, source/synthetic separation and separate check/incident commits. Counts are observations, not affected bookings. Healthy checks cannot resolve incidents. Only validated, cited and individually supported hypotheses/recommendations can be stored as assessments against linked evidence. Root cause remains explicitly unknown; never turn a 401 into credential expiry. Migration head is 0003_incident_assessments. No background scheduler or retry/reconciliation exists.
- Application storage is separate from monitored POSTGRES_* credentials. Run migrations explicitly; do not auto-migrate on startup or add arbitrary SQL/HTTP migration endpoints. Keep synthetic/live identities separate. The initial schema blocks incident resolution until a verified recovery workflow and later migration exist.
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
