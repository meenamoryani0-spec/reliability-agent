# n8n Error Trigger reporting

This is an alternative to public API polling, not a replacement for all API
features. n8n Cloud trials do not include the public API. An Error Trigger
workflow can instead send minimal notifications to this application's backend.

## Data and authority

The fixed HTTPS destination is `/integrations/n8n/failures` on the configured
Reliability backend. The JSON body contains exactly two string fields:

```json
{"workflow_id":"registered-workflow-id","execution_id":"123"}
```

No customer payload, error message, stack trace, node output or secret is accepted.
The schema rejects extra fields, duplicate JSON keys, invalid IDs and bodies over
1,024 bytes. Only configured workflow IDs are accepted. An event means **n8n
reported a failed execution**; the receiver does not independently poll n8n.
The timestamp is receipt time, not execution time. The event cannot establish
node-level cause, customer outcome or recovery.

`N8N_EVENTS_TOKEN` must be a separate generated URL-safe secret with at least
32 bytes of entropy. It authenticates only this POST route and cannot read
history, register targets, investigate, retry or change workflows. The normal
backend bearer key is rejected by this route; the event key is rejected by the
production operator API. Browser origins are denied. TLS verification stays on.

Configuration is disabled by default:

```dotenv
N8N_EVENTS_ENABLED=false
N8N_EVENTS_TOKEN=
N8N_EVENTS_WORKFLOW_IDS=[]
N8N_BASE_URL=
```

Enable only with migrated history storage, an exact `/api/v1/` source URL, an
explicit workflow allowlist and a dedicated token. This source URL is an
identity boundary; receiving reports does not call that API. Source identities
are separate from API polls and fixtures. No schema migration beyond 0006 is
needed. Existing history privileges suffice.

## Setup and acceptance

1. Review the inactive Error Trigger → saved-ID filter → fixed HTTP POST draft.
   It is in the user's Personal project, at the project root. Existing business
   workflows have not been attached or changed by creating the draft.
2. Configure the dedicated ingest token privately in Render and a matching n8n
   HTTP credential. Use `Authorization: Bearer <ingest token>`. Never use the
   dashboard/operator/backend service key. Do not put a token in node parameters,
   a URL, source control or chat.
3. Set `N8N_EVENTS_ENABLED=true`, `N8N_BASE_URL` to the exact instance API root,
   and `N8N_EVENTS_WORKFLOW_IDS` to explicitly approved workflow IDs.
4. Validate delivery with a separate disposable test workflow. Do not deliberately
   break or replay a business workflow. Only then attach the reporter through
   each approved workflow's Error workflow setting. Preserve an existing handler
   rather than replacing it silently. Check publishing requirements for the
   installed n8n version.
5. Inspect Connections → Load received failure reports and the saved Checks
   history. Verify repeated delivery preserves the same check ID and first
   receipt time. With incident creation enabled, repeated reports link once to
   the same unresolved incident. Incident-write failure does not erase the check;
   repeat delivery may safely finish that separate incident step.

The model gets one additional bounded **read** tool only when reporting is
enabled. It reads up to 25 saved notifications for registered workflow sources.
It cannot register a reporter or ingest arbitrary events. Notifications support
only a reported workflow failure; HTTP-status diagnoses still require node
evidence. Production repair/retry/resolve remain disabled.

## Coverage limits

- No historical backfill, workflow enumeration, success heartbeat or API polling.
- No manual-run coverage guarantee. Failures in trigger nodes may have no saved
  execution ID and are excluded by the saved-ID filter.
- A missing notification can mean no failure, a disconnected reporter, an
  unsupported failure type, or a delivery failure. It never proves health.
- Render free-tier sleep and provider limits can delay or prevent delivery.
- This does not implement an always-on scheduler or verify customer flows.
- Retrying the report is safe for duplicate observation count. Retrying the
  original business execution is a separate, consequential operation.

## Primary references

- [n8n public API availability during trials](https://support.n8n.io/article/can-i-have-api-access-while-im-on-a-trial)
- [n8n Error Trigger workflow setup and payload](https://docs.n8n.io/build/flow-logic/handle-errors-gracefully.md)

The SDK draft was validated with the connected n8n tool and its filter was tested
with synthetic pinned data. The HTTP node was pinned during that test, so this
is not proof of live delivery. Live activation needs the private credential and
a separate end-to-end delivery test.
