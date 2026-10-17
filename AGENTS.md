# Project implementation instructions

Read README.md and docs/HANDOFF.md before extending the application.

- Keep all new project files, virtual environments, caches, and logs on D:.
- Build incrementally and run each component and its local tests before extending it.
- User clarification on 2026-10-10: API credentials must not block local development. Use mocks/local fixtures; defer real provider tests until credentials are supplied.
- Phases 1 and 3–9 are locally verified. Phase 9 adds a bounded model/tool investigation loop and 97 tests. Final run: 608 passed, no skips, including isolated PostgreSQL and real Chromium; lint/format/pip and actual Uvicorn fixture investigation smoke pass. The unchanged PostgreSQL harness now succeeds in this execution environment after Phase 8's initialization timeout; its earlier failure cause remains unverified. Live Nemotron/tool calling, monitoring providers and the separate Phase 6 monitored PostgreSQL probe remain unverified. Next: Phase 10 — autonomous incident creation. Read docs/PHASE-9.md and docs/CURRENT-STATE.md.
- Registry execution stays internal; GET /tools is a local catalog only. Preserve strict schemas, byte/deadline limits, fixture flags, history failure separation and occupied slots until timed-out/cancelled adapter work finishes. No production registry access before deployment controls; no arbitrary shell/SQL/URL or remediation tools.
- Investigation defaults to disabled. Fixture inference is explicitly scripted and requires n8n/infrastructure fixtures; no live website tools in this mode. Live inference is opt-in and sends the question/restricted evidence to Nebius. Keep 6-turn/8-tool/120-second limits, supported citations/conclusions, production rejection and cancellation draining. No model prose as verified cause, automatic incidents or remediation in Phase 9.
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
