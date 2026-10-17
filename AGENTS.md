# Project implementation instructions

Read README.md and docs/HANDOFF.md before extending the application.

- Keep all new project files, virtual environments, caches, and logs on D:.
- Build incrementally and run each component and its local tests before extending it.
- User clarification on 2026-10-10: API credentials must not block local development. Use mocks/local fixtures; defer real provider tests until credentials are supplied.
- Phases 1, 3, 4, 5, and 6 are verified locally. Phase 6 adds read-only Vercel/Supabase checks and a process-isolated PostgreSQL probe; tests/backend HTTP use provider/driver fixtures. Live Vercel, Supabase, PostgreSQL, n8n and Nebius connections remain unverified. Website checks previously passed an example.com smoke; Chromium flows are synthetic fixtures. Next is Phase 7 — database persistence. See docs/PHASE-6.md and docs/CURRENT-STATE.md.
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
