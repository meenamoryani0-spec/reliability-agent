# Phase 2 — implemented; real connectivity awaiting credentials

Verified documentation and implementation on 9 October 2026 (Asia/Calcutta).

## Status

- Complete automated suite: **54 passed** (mocked adapter plus existing backend tests).
- Ruff lint and formatting: PASS.
- Real local backend HTTP smoke: PASS (health, docs, OpenAPI).
- Nebius live command: **NOT_VERIFIED — missing_api_key**.
- No real provider request has succeeded; Phase 2 remains incomplete.
- No Phase 3 monitoring adapter, tool registry, incident, or agent loop was started.

## Hackathon findings

The [official rules](https://nebiusglobalaihackathon.devpost.com/rules) allow a
runtime Token Factory inference call to satisfy the Nebius usage requirement;
Nebius application hosting is optional. Submissions must use an NVIDIA open
source model. **Recommendation:** this project fits the Best Apps and Agents
track because its core capability is investigating business workflow failures.
Track fit is our interpretation, not organizer approval of this submission.

The submission deadline is 30 October 2026 at 10:00 am PDT, equivalent to
**30 October 2026 at 10:30 pm IST**. Future submission work needs a working demo,
a public repository with an open source license, and a video no longer than
three minutes. A repository license has not yet been selected.

## API and model verification

- [Nebius model page](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference)
  currently identifies `nvidia/Nemotron-3_5-Lightning` with a public endpoint.
  This confirms the handoff's model identifier in provider documentation.
- [Quickstart](https://docs.tokenfactory.nebius.com/quickstart) documents the
  OpenAI-compatible API base `https://api.tokenfactory.nebius.com/v1/`.
- [Chat completion reference](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion)
  confirms POST `/v1/chat/completions`, Bearer authorization, model/messages,
  max_tokens, stream/store flags, and assistant content/finish_reason fields.
- [Model catalog reference](https://docs.tokenfactory.nebius.com/api-reference/models/list-models)
  confirms GET `/v1/models` and the response's data entries with model IDs.

The marketing page's example omits `/v1/`; the implementation follows the
explicit API reference and quickstart. The interactive model catalog could not
be extracted by the web tool. Model access with this user's API key is still
unverified; the live command checks it before making an inference request.

## Files created or updated

Created: `backend/app/agent/{__init__,client,smoke}.py`,
`backend/tests/test_nebius.py`, `scripts/nebius-smoke.ps1`, this report, and an
ignored local `.env` copied from the template when none existed.

Updated: settings and config tests, `.env.example`, runtime/development
dependency inputs and hash lockfiles, explicit Ruff first-party import
configuration, project instructions, and README.

The client sends credentials only in the Authorization header to the fixed
official HTTPS host. Redirects and environment-provided proxies are disabled.
Requests have an overall deadline, an output token cap, and a 1 MiB response
limit. Raw provider errors and transport exception messages are suppressed.
No public inference HTTP route is exposed at this phase.

## Commands and test coverage

```powershell
. .\scripts\environment.ps1
uv pip compile backend\requirements.in --python $ProjectPython --generate-hashes --output-file backend\requirements.txt --offline
uv pip compile backend\requirements-dev.in --constraint backend\requirements.txt --python $ProjectPython --generate-hashes --output-file backend\requirements-dev.txt --offline
.\scripts\test.ps1
.\scripts\smoke.ps1
.\scripts\nebius-smoke.ps1
```

Dependencies were already installed in Phase 1, so resolution needed no new
downloads. Tests exercise documented request shape, authentication placement,
catalog checks, HTTP error classification, no redirects/retries, malformed
responses, empty/truncated output, model mismatch, size limits, transport
failures, overall deadline, prompt limits, configuration bounds, and masked
secrets. No real credentials appear in tests.

The first test execution hung while Windows asyncio created its internal local
socket pair. A timed traceback identified `socket._fallback_socketpair` as the
blocking point. After granting network access for the execution environment,
the async tests and backend smoke passed. The old hung executions were stopped.

## Required next input

Save `NEBIUS_API_KEY` in the ignored local `.env` and run the live command.
Do not claim phase completion or continue to Phase 3 based on mocked tests.
