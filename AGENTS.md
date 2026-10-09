# Project implementation instructions

Read README.md and docs/HANDOFF.md before extending the application.

- Keep all new project files, virtual environments, caches, and logs on D:.
- Build incrementally; complete and verify each phase before starting the next.
- Current scope is Phase 1 only. Phase 2 requires fresh official Nebius/model verification.
- Follow the handoff's Python/FastAPI backend-first order; no empty future modules.
- Check current official provider documentation before implementing API adapters.
- Keep credentials in environment variables; never commit .env or print secrets.
- Separate read checks from write actions. No arbitrary shell or SQL tools for the model.
- Unknown/check-failed is different from unhealthy. Require evidence for root causes.
- Never resolve an incident without successful recovery verification.
- Run scripts/test.ps1 and a live HTTP smoke test for backend milestones.
- Commit verified stable milestones; report untested integrations accurately.
- Docker is optional until the backend host is chosen; it is not needed for Phase 1.
