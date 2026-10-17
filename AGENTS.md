# Project implementation instructions

Read README.md and docs/HANDOFF.md before extending the application.

- Keep all new project files, virtual environments, caches, and logs on D:.
- Build incrementally and run each component and its local tests before extending it.
- User clarification on 2026-10-10: API credentials must not block local development. Use mocks/local fixtures; defer real provider tests until credentials are supplied.
- Phases 1, 3, 4, 5, 6, and 7 are locally verified. Phase 7 adds SQLAlchemy/Alembic history storage; 438 tests pass including real isolated PostgreSQL and SQLite. Backend restart persistence is verified; local history is enabled in ignored .env. Cloud/provider connections remain unverified; the Phase 6 monitored PostgreSQL probe still lacks live provider validation. Next is Phase 8 — tool registry. See docs/PHASE-7.md and docs/CURRENT-STATE.md.
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
