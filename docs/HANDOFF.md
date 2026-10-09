=== HANDOFF: READ FIRST ===

You are taking over a software project from another AI conversation.

Everything below is the established project context.

Treat:
- [FACT] as stated or verified.
- [DECISION] as settled unless a technical blocker is discovered.
- [ASSUMPTION] as unverified.
- [OPINION] as guidance, not fact.
- UNCLEAR means confirmation may be required.

IMPORTANT:
Do not repeatedly ask me questions that are already answered below.

I want you to act as the IMPLEMENTATION ENGINEER.

I do NOT want to manually write the application code.

You should:
- create files
- edit files
- create the repository structure
- install dependencies
- run terminal commands
- run the application
- run tests
- inspect errors
- debug errors
- fix errors
- maintain Git
- prepare deployment
- document setup

Do not merely explain what code I should write.

BUILD IT.

Work incrementally.

Do not generate an enormous fake project where half the files contain placeholders.

Each major component must actually run before you proceed.

If an external API or SDK is involved:
1. Check its current official documentation.
2. Verify endpoint names, authentication, request schema, response schema, SDK methods and current model IDs.
3. Never invent API endpoints or capabilities.
4. If something cannot be verified, mark it clearly instead of guessing.

Security:
- Never hard-code credentials.
- Never print secrets.
- Never commit .env.
- Create .env.example.
- Use environment variables.
- Separate READ operations from WRITE/remediation operations.
- Never give the AI unrestricted shell access.
- Never give the AI unrestricted production database modification access.
- Never allow destructive production actions without an explicit policy/approval layer.

After every milestone:
1. run the relevant application
2. run tests
3. inspect failures
4. fix failures
5. show what was created
6. show what works
7. show what remains
8. commit stable changes if Git is initialized

Do not pretend something works if it has not actually been tested.

=== END ===


=== BLOCK: GOAL ===

[FACT]
The project is intended for an NVIDIA × Nebius AI hackathon.

[DECISION]
Build an AI Reliability Agent.

[DECISION]
The product should monitor:
1. websites
2. n8n/business automations
3. supporting infrastructure

[DECISION]
The AI should be able to:

DETECT
→ INVESTIGATE
→ CORRELATE EVIDENCE
→ IDENTIFY ROOT CAUSE
→ CREATE INCIDENT
→ RECOMMEND OR EXECUTE AN APPROVED SAFE ACTION
→ VERIFY RECOVERY

[DECISION]
The project should demonstrate real agentic behavior instead of being a normal monitoring dashboard with a chatbot attached.

=== END ===


=== BLOCK: CORE PRODUCT DEFINITION ===

[DECISION]

Use this as the primary project definition:

"Build an NVIDIA Nemotron-powered AI reliability agent on Nebius that monitors a client's website, n8n business automations, and supporting infrastructure, autonomously investigates failures across them, identifies root causes, creates incidents, recommends or safely executes remediation, and verifies that the system is working again."

The user/business owner should be able to ask questions such as:

"Why are customers not receiving booking confirmations?"

The system should NOT simply answer from an LLM.

It should inspect actual operational systems using tools and gather evidence.

Example reasoning flow:

User:
"Why are bookings failing?"

Agent:
→ inspect n8n executions
→ find failed booking workflow
→ inspect failed execution
→ identify failed Google Calendar/CRM/API node
→ check database/infrastructure if relevant
→ check website if relevant
→ rule out unrelated systems
→ determine root cause
→ create incident
→ recommend action
→ after remediation, run verification
→ close incident only if verification succeeds

=== END ===


=== BLOCK: IMPORTANT ARCHITECTURE CLARIFICATION ===

[FACT]
The WhatsApp AI Agent is itself implemented using n8n.

[DECISION]
Do NOT treat "WhatsApp AI Agent" as a completely separate top-level monitoring platform.

It is a major use case inside the n8n/business automation monitoring category.

The three top-level areas are:

1. WEBSITE

Examples:
- uptime
- HTTP status
- response time
- frontend errors
- APIs
- forms
- browser flows
- SSL
- DNS
- deployments

2. N8N / BUSINESS AUTOMATION

Examples:
- WhatsApp AI Agent workflow
- lead automation
- appointment booking
- CRM workflow
- Google Calendar integration
- email workflow
- database workflow
- custom client workflows
- execution failures
- failed nodes
- credential errors
- API errors

3. INFRASTRUCTURE

Examples:
- Vercel
- Supabase
- PostgreSQL
- VPS/server
- external APIs
- authentication
- environment/configuration problems
- DNS/SSL where appropriate

[DECISION]
"Incident Management" is NOT a fourth monitored service.

An incident is the record/process created when something important breaks.

=== END ===


=== BLOCK: TARGET SYSTEM ARCHITECTURE ===

[DECISION]

Target architecture:

                     USER
                      │
                      ▼
              Web Dashboard / Chat
                      │
                      ▼
               AI AGENT / ORCHESTRATOR
                      │
           NVIDIA Nemotron via Nebius
                      │
                TOOL CALLING
                      │
                      ▼
              PYTHON OPERATIONS API
                  FastAPI
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
     WEBSITE         N8N      INFRASTRUCTURE
      TOOLS          TOOLS          TOOLS
        │             │             │
        └─────────────┼─────────────┘
                      │
                    EVIDENCE
                      │
                      ▼
                   NEMOTRON
                      │
                      ▼
                 ROOT CAUSE
                      │
                      ▼
                 INCIDENT
                      │
                      ▼
             APPROVED SAFE ACTION
                      │
                      ▼
                 VERIFICATION

=== END ===


=== BLOCK: TECH STACK ===

[DECISION]
Primary backend programming language:
Python

[DECISION]
Backend web framework:
FastAPI

[DECISION]
Data validation/settings:
Pydantic / Pydantic Settings

[DECISION]
Async HTTP client:
HTTPX

[DECISION]
Browser automation/testing:
Playwright Python

[DECISION]
AI provider:
Nebius Token Factory

[DECISION]
AI model family:
NVIDIA Nemotron

[ASSUMPTION]
Previously discussed model:
nvidia/Nemotron-3_5-Lightning

Before implementing the AI integration, verify the CURRENT eligible/current model ID in official Nebius/hackathon documentation.

Do not blindly assume the model ID remains unchanged.

[DECISION]
Nebius should be accessed using its current supported API/SDK.

An OpenAI-compatible API was previously discussed.

Verify the current official API documentation before coding.

[DECISION]
Automation platform:
n8n

[DECISION]
Automation monitoring:
n8n Public REST API

[DECISION]
Database:
PostgreSQL

[DECISION]
Preferred managed database:
Supabase PostgreSQL

[DECISION]
Python PostgreSQL access:
SQLAlchemy + asyncpg is acceptable.

[DECISION]
Frontend framework:
Next.js

[DECISION]
Frontend language:
TypeScript

[DECISION]
Frontend styling:
Tailwind CSS is acceptable.

[DECISION]
Frontend deployment:
Vercel

[DECISION]
Source control:
Git + GitHub

[DECISION]
Containerization:
Docker

[ASSUMPTION]
Backend deployment can use a Docker-capable service such as:
- Railway
- Render
- VPS

Exact backend hosting provider has NOT been permanently settled.

Choose a simple Docker-capable deployment option appropriate for the project unless one is specified later.

[DECISION]
DNS checking:
dnspython or equivalent verified Python library

[DECISION]
SSL checking:
Python ssl/socket or equivalent

[ASSUMPTION]
Periodic monitoring:
APScheduler was discussed.

Use it only if it remains appropriate.
Do not add background infrastructure unnecessarily.

=== END ===


=== BLOCK: DO NOT ADD WITHOUT A REASON ===

[DECISION]
Do NOT initially add:

- Kubernetes
- Kafka
- Redis unless required
- a vector database unless required
- multi-agent swarms
- unnecessary microservices
- AWS monitoring
- Azure monitoring
- GCP monitoring
- every possible CRM
- every possible cloud platform
- fine-tuning
- autonomous arbitrary code rewriting
- unrestricted terminal access for the AI

[DECISION]
LangChain is NOT required for the MVP.

Use direct SDK/API integration unless an agent framework provides a clear measurable advantage.

Avoid abstraction for abstraction's sake.

=== END ===


=== BLOCK: BACKEND STRUCTURE ===

[DECISION]

Start approximately with this structure, but improve it if there is a technically justified reason:

reliability-agent/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   │
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── diagnose.py
│   │   │   ├── incidents.py
│   │   │   └── services.py
│   │   │
│   │   ├── agent/
│   │   │   ├── client.py
│   │   │   ├── orchestrator.py
│   │   │   ├── prompts.py
│   │   │   └── tool_registry.py
│   │   │
│   │   ├── tools/
│   │   │   ├── website.py
│   │   │   ├── browser.py
│   │   │   ├── dns.py
│   │   │   ├── ssl.py
│   │   │   ├── n8n.py
│   │   │   ├── vercel.py
│   │   │   └── supabase.py
│   │   │
│   │   ├── incidents/
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   └── service.py
│   │   │
│   │   ├── db/
│   │   │   ├── database.py
│   │   │   ├── models.py
│   │   │   └── migrations/
│   │   │
│   │   ├── config.py
│   │   └── logging.py
│   │
│   ├── tests/
│   ├── requirements.txt OR pyproject.toml
│   └── Dockerfile
│
├── frontend/
│
├── .env.example
├── .gitignore
├── docker-compose.yml
├── README.md
└── LICENSE

Do not mechanically create this entire tree with empty files.

Create files when they become necessary.

=== END ===


=== BLOCK: TOOL DESIGN ===

[DECISION]
The AI must interact with infrastructure through explicit controlled tools.

Possible READ tools:

check_website_health()
check_website_endpoint()
test_website_flow()
check_ssl()
check_dns()

list_n8n_workflows()
list_failed_n8n_executions()
get_n8n_execution()

check_vercel_deployment()
get_vercel_deployment_events()

check_supabase_health()
check_postgres()

create_incident()
get_incident()

verify_service()
run_test_workflow()

[DECISION]
WRITE/remediation tools must be separate from READ tools.

Possible WRITE tool:

retry_n8n_execution()

Other write tools may be added later only when justified and protected.

[DECISION]
Do not expose arbitrary shell execution as an AI tool.

[DECISION]
Do not expose unrestricted SQL write access as an AI tool.

=== END ===


=== BLOCK: NORMALIZED TOOL OUTPUT ===

[DECISION]
Provider-specific responses should be normalized before being given to the reasoning model.

Preferred common structure:

{
  "service": "n8n",
  "component": "booking-workflow",
  "healthy": false,
  "severity": "high",
  "summary": "Workflow execution failed",
  "evidence": {
    "execution_id": "4921",
    "status": "error",
    "failed_node": "Google Calendar",
    "error": "Authentication failed"
  }
}

Another example:

{
  "service": "website",
  "component": "contact-form",
  "healthy": true,
  "severity": "none",
  "summary": "Contact form works normally",
  "evidence": {}
}

The AI should reason over normalized evidence instead of giant uncontrolled provider payloads whenever practical.

=== END ===


=== BLOCK: WEBSITE MONITORING ===

[DECISION]
Website monitoring should have multiple layers.

Layer 1:
HTTP availability

Check:
- HTTP status
- redirects
- latency
- basic endpoint health

Use:
HTTPX

Layer 2:
real browser/business-flow testing

Use:
Playwright Python

Examples:
- open website
- navigate page
- fill contact form
- submit form
- detect success/failure
- capture browser console errors
- observe failed requests if useful

Layer 3:
SSL/DNS

Check:
- DNS resolution
- certificate availability
- certificate expiry/details where technically appropriate

Layer 4:
deployment/platform evidence

Initial target:
Vercel API/events/logs where available through official API.

Example diagnosis:

Homepage: healthy
Contact page: healthy
Contact form: fails
/api/contact: HTTP 500
Deployment/runtime evidence: configuration/env problem

AI conclusion:
The public website is reachable, but the lead submission backend is failing.

=== END ===


=== BLOCK: N8N MONITORING ===

[DECISION]
n8n is one of the core monitored systems.

The agent should eventually be able to inspect:

- workflows
- execution history
- failed executions
- execution details
- failed node
- error data
- credential/authentication errors
- API failures
- timeouts
- rate limits
- webhook failures

[FACT]
Previously discussed n8n Public API authentication:

X-N8N-API-KEY

[FACT]
Previously discussed base structure:

https://YOUR-N8N/api/v1

[FACT]
Previously discussed operations included:

GET /api/v1/workflows

GET /api/v1/workflows/{id}

GET /api/v1/executions

GET /api/v1/executions?status=error

GET /api/v1/executions/{id}?includeData=true

POST /api/v1/executions/{id}/retry

POST /api/v1/audit

IMPORTANT:
Before implementation, verify these against the CURRENT official n8n documentation/API specification.

Do not assume endpoints remain unchanged merely because they appeared in the earlier conversation.

[FACT]
n8n security audit was discussed as capable of identifying categories involving credentials, database/filesystem, nodes and instance configuration.

[FACT]
Security audit permissions may require elevated/owner access.

Do not assume all clients will permit that operation.

=== END ===


=== BLOCK: WHATSAPP USE CASE ===

[FACT]
The WhatsApp AI Agent is built with n8n.

[DECISION]
Treat WhatsApp as an n8n/business workflow use case rather than a completely separate architecture.

Example business workflow:

Customer WhatsApp message
↓
WhatsApp/Meta API
↓
n8n webhook
↓
AI Agent
↓
Lead qualification
↓
Google Calendar
↓
CRM
↓
Confirmation

Example failure:

WhatsApp trigger       success
AI Agent               success
Calendar               success
CRM                    failure
Confirmation           not executed

AI should identify:
"The WhatsApp agent is working. The failure occurred at the CRM step."

=== END ===


=== BLOCK: INFRASTRUCTURE MONITORING ===

[DECISION]
Initial infrastructure scope should remain limited.

Initial targets:

- Vercel
- Supabase
- PostgreSQL
- optionally the backend server/VPS
- important external APIs

Do not attempt to support every cloud provider in the MVP.

Vercel monitoring may include:
- current deployment
- deployment status
- deployment/build events
- failures

Supabase monitoring may include:
- project/platform health
- database connectivity

PostgreSQL should also be tested directly, for example with a simple safe query such as:

SELECT 1

Reason:
Platform health being green does not guarantee application credentials or database connectivity are correct.

=== END ===


=== BLOCK: INCIDENT SYSTEM ===

[DECISION]
An incident represents a detected operational problem.

Suggested incident fields:

id
client_id
title
service
component
severity
status
detected_at
root_cause
evidence
recommended_action
action_taken
verified
resolved_at

[DECISION]
Use PostgreSQL/Supabase to store incidents.

Example incident:

INCIDENT #17

Problem:
Customers cannot book appointments.

Website:
Healthy

n8n:
Booking workflow failing

Infrastructure:
Healthy

Root Cause:
Google Calendar authentication expired

Affected:
7 booking attempts

Recommended Action:
Reconnect Google Calendar credentials

Verification:
Run a test booking after the fix

Status:
OPEN

[DECISION]
Never mark an incident RESOLVED only because an action API returned success.

The system must verify the business flow again.

=== END ===


=== BLOCK: AGENT BEHAVIOR ===

[DECISION]
The AI agent must follow evidence rather than guess.

Example:

User:
"Why aren't WhatsApp bookings working?"

Agent:

1.
check_n8n_failed_executions()

2.
Find booking workflow failure.

3.
get_n8n_execution(execution_id)

4.
Find:
Google Calendar / CRM / relevant node authentication error.

5.
If needed:
check_postgres()

6.
If needed:
check_website_health()

7.
If needed:
check relevant infrastructure.

8.
Correlate results.

9.
Identify actual root cause.

10.
Create incident.

The model should clearly distinguish:

CONFIRMED CAUSE

from:

POSSIBLE CAUSE

Do not let it manufacture certainty.

=== END ===


=== BLOCK: REMEDIATION SAFETY ===

[DECISION]
Start with ONE controlled remediation action.

Preferred first example:

retry_n8n_execution(execution_id)

[DECISION]
Architecture:

READ TOOLS
↓
AI diagnosis
↓
PROPOSED WRITE ACTION
↓
POLICY CHECK
↓
HUMAN APPROVAL IF REQUIRED
↓
EXECUTE WRITE TOOL
↓
VERIFY
↓
RESOLVE INCIDENT ONLY IF VERIFIED

[DECISION]
Potentially dangerous actions must require approval.

Examples:
- modifying environment variables
- changing production code
- editing workflows
- modifying production database data
- deleting resources

=== END ===


=== BLOCK: VERIFICATION ===

[DECISION]
Verification is mandatory.

Example:

Workflow failed
↓
retry_n8n_execution()
↓
new execution created
↓
inspect execution result
↓
run end-to-end test if relevant
↓
only if successful:
Incident = RESOLVED

The AI must NOT say:
"Fixed"

merely because:
"Retry request returned HTTP 200."

=== END ===


=== BLOCK: DATABASE ===

[DECISION]
Use PostgreSQL via Supabase for the agent's own persistent state.

At minimum store:

1. monitored_services
2. checks
3. incidents

Possible checks table:

id
service
component
check_type
healthy
latency_ms
data
checked_at

Possible monitored_services table:

id
name
service_type
configuration
enabled

Sensitive credentials must NOT be stored as plaintext inside arbitrary JSON configuration.

Design secrets handling correctly.

=== END ===


=== BLOCK: FRONTEND ===

[DECISION]
Build the UI only after the backend/core agent works.

Use:
Next.js + TypeScript

Host:
Vercel

Initial dashboard only needs:

- Website status
- n8n status
- Infrastructure status
- Active incidents
- Incident severity
- Root cause
- Evidence
- Recommended action
- approval/action control where applicable
- verification state
- simple "Ask Reliability Agent" input

Do NOT waste the hackathon building a huge enterprise dashboard.

Possible UI concept:

┌───────────────────────────────────────────┐
│ AI RELIABILITY AGENT                      │
├───────────────────────────────────────────┤
│ Website          ● Healthy                │
│ n8n              ● Problem                │
│ Infrastructure   ● Healthy                │
├───────────────────────────────────────────┤
│ ACTIVE INCIDENT                           │
│                                           │
│ Booking workflow failure                  │
│                                           │
│ Root Cause                                │
│ CRM authentication failure                │
│                                           │
│ Affected executions: 7                    │
│                                           │
│ [View Evidence] [Approve Fix]              │
└───────────────────────────────────────────┘

=== END ===


=== BLOCK: ENVIRONMENT VARIABLES ===

[DECISION]
Maintain .env.example.

Likely categories:

# Nebius
NEBIUS_API_KEY=
NEBIUS_MODEL=

# n8n
N8N_BASE_URL=
N8N_API_KEY=

# Vercel
VERCEL_ACCESS_TOKEN=
VERCEL_PROJECT_ID=
VERCEL_TEAM_ID=

# Supabase
SUPABASE_PROJECT_REF=
SUPABASE_ACCESS_TOKEN=

# PostgreSQL
DATABASE_URL=

# Application
ENVIRONMENT=
LOG_LEVEL=

Names may change if official APIs or implementation choices require it.

Never commit real values.

=== END ===


=== BLOCK: DEPLOYMENT MODEL ===

[DECISION]

Development:

Local repository
↓
Codex edits repository
↓
Codex runs Python/Node/tests
↓
Git

Version control:

Local Git
↓
GitHub

Production:

GitHub
├── frontend → Vercel
└── backend → Docker-compatible hosting

Database:
Supabase PostgreSQL

AI:
Nebius Token Factory / NVIDIA Nemotron

External monitored systems:
n8n
Vercel
Supabase/Postgres
website

[ASSUMPTION]
Backend provider is not finally chosen.

Choose the simplest suitable Docker-capable deployment platform when deployment is reached.

Do not make backend hosting the first problem.

=== END ===


=== BLOCK: CODING WORKFLOW ===

[DECISION]
I want to use AI-assisted/vibe coding heavily.

I do NOT want to manually implement every file.

Your role is to actually manipulate the repository and run the software.

My role is primarily:
- define requirements
- provide required credentials/configuration
- inspect results
- approve important architecture/security decisions
- test business behavior

Your role:
- code
- test
- debug
- refactor
- document
- deploy/configure when possible

IMPORTANT:
Do not dump hundreds of lines of code into chat and tell me to manually paste them into ten files if you have filesystem/repository access.

Modify the repository directly.

=== END ===


=== BLOCK: BUILD ORDER ===

[DECISION]
Follow this order unless you discover a strong technical reason to adjust it.

PHASE 1 — FOUNDATION

Create:
- repository structure
- Python backend
- FastAPI app
- configuration system
- logging
- .env.example
- .gitignore
- test setup

Implement:

GET /health

Required result:
backend runs locally
/health returns success
tests pass

STOP AND VERIFY.


PHASE 2 — NEBIUS / NEMOTRON

Verify official current documentation.

Implement:
- Nebius client
- current eligible NVIDIA Nemotron model
- one simple AI request
- test/error handling

Required result:
backend can successfully communicate with Nemotron.

STOP AND VERIFY.


PHASE 3 — WEBSITE CHECKER

Implement:
- HTTP health check
- HTTP latency
- endpoint check
- SSL check
- DNS check

Tests required.

STOP AND VERIFY.


PHASE 4 — PLAYWRIGHT

Implement:
- browser launch
- page navigation
- one test business flow
- console error collection
- failure reporting

Required result:
one healthy flow
one intentionally failing flow

STOP AND VERIFY.


PHASE 5 — N8N INTEGRATION

Verify current n8n official API documentation.

Implement:
- authentication
- list workflows
- list failed executions
- fetch execution details
- normalize execution error data

Do NOT implement destructive actions yet.

STOP AND VERIFY.


PHASE 6 — INFRASTRUCTURE

Implement:
- Vercel deployment check
- Vercel deployment/event evidence where supported
- Supabase/project health where supported
- PostgreSQL connectivity

Normalize outputs.

STOP AND VERIFY.


PHASE 7 — DATABASE

Create persistent models/migrations for:
- monitored services
- checks
- incidents

Implement repository/service layer.

STOP AND VERIFY.


PHASE 8 — TOOL REGISTRY

Expose confirmed working checks as AI tools.

Tools should have:
- strict schemas
- clear descriptions
- deterministic validation
- normalized outputs
- timeout/error handling

STOP AND VERIFY.


PHASE 9 — AGENT LOOP

Implement agent orchestration.

Required behavior:

User question
↓
model chooses tool
↓
tool executes
↓
structured evidence returned
↓
model decides whether more evidence is necessary
↓
additional tools if justified
↓
model concludes when evidence is sufficient

Prevent infinite tool loops.

Add maximum steps/time/tool-call safeguards.

STOP AND VERIFY.


PHASE 10 — INCIDENT CREATION

When diagnosis meets confidence/evidence requirements:

create incident
store evidence
store root cause
store severity
store recommendation

STOP AND VERIFY.


PHASE 11 — FIRST WRITE ACTION

Implement only:

retry_n8n_execution(execution_id)

Protect it with:
- explicit policy
- input validation
- approval requirement if appropriate

STOP AND VERIFY.


PHASE 12 — VERIFICATION LOOP

After remediation:

inspect new n8n execution
and/or
run relevant business-flow test

Only mark resolved if verification succeeds.

STOP AND VERIFY.


PHASE 13 — FRONTEND

Build small Next.js dashboard.

Integrate backend.

Show:
- service health
- incidents
- diagnosis
- evidence
- recommended action
- approval
- verification

STOP AND VERIFY.


PHASE 14 — DEPLOYMENT

Prepare:
- production Dockerfile
- environment configuration
- CORS/security
- health checks
- startup commands

Deploy:
frontend → Vercel
backend → chosen Docker-compatible service
database → Supabase

Run production smoke tests.

STOP AND VERIFY.


PHASE 15 — HACKATHON DEMO

Build one excellent intentional failure scenario.

Do not create twenty shallow demos.

=== END ===


=== BLOCK: PRIMARY DEMO SCENARIO ===

[DECISION]
Strong demo candidate:

Customer:
WhatsApp booking request

Flow:

WhatsApp
↓
n8n
↓
AI Agent
↓
Google Calendar
↓
CRM
↓
Confirmation message

Intentionally cause ONE controlled integration failure.

Example:
CRM authentication failure.

Visible symptom:
customer receives no booking confirmation.

Business owner asks:

"Why are customers not receiving booking confirmations?"

Reliability Agent:

1. checks recent n8n failures
2. locates booking workflow
3. inspects failed execution
4. identifies CRM node failure
5. checks relevant infrastructure
6. rules out database/website/other systems where necessary
7. determines root cause
8. creates incident
9. shows evidence
10. recommends fix

After issue is corrected:

11. retry/test workflow
12. verify success
13. resolve incident

The demonstration should make the agent's investigation visible.

=== END ===


=== BLOCK: SECONDARY DEMO SCENARIO ===

[DECISION]
Possible second demo if time allows:

Website lead flow:

Website
↓
Contact Form
↓
API
↓
n8n
↓
CRM

Failure:

contact/API layer fails.

Agent should:

check homepage
↓
healthy

test form via Playwright
↓
fails

inspect HTTP/API result
↓
500/error

inspect deployment evidence if available
↓
identify likely/confirmed configuration/runtime problem

Root cause must be evidence-backed.

=== END ===


=== BLOCK: QUALITY REQUIREMENTS ===

[DECISION]

Every important backend subsystem needs tests.

Prefer:
- unit tests for deterministic utilities
- integration tests for API adapters where practical
- mocked external API tests
- at least some real smoke tests against configured services

External API adapters must handle:
- timeouts
- authentication failures
- HTTP errors
- malformed responses
- rate limits where relevant

The agent must never convert:

"tool unavailable"

into:

"service is broken"

These are different states.

Normalize states such as:

HEALTHY
UNHEALTHY
DEGRADED
UNKNOWN
CHECK_FAILED

Do not confuse UNKNOWN with UNHEALTHY.

=== END ===


=== BLOCK: SECURITY REQUIREMENTS ===

[DECISION]

Apply least privilege.

READ credentials:
only permissions necessary to inspect systems.

WRITE credentials:
only permissions necessary for the specific approved remediation.

Never:
- expose tokens to the browser
- send secrets to Nemotron
- put production secrets in prompts
- commit secrets to Git
- log raw credentials
- permit arbitrary user-controlled URLs without SSRF protections
- permit arbitrary SQL
- permit arbitrary shell commands

Be particularly careful with:
- Playwright
- user-supplied URLs
- webhook inputs
- server-side requests
- log content passed to the LLM

Treat external logs/content as untrusted data.

=== END ===


=== BLOCK: PRODUCT DIFFERENTIATION ===

[DECISION]
This project is NOT intended to be:

- another uptime monitor
- another log viewer
- another n8n dashboard
- another chatbot

The interesting capability is:

The AI can investigate multiple connected systems to determine why an actual business process failed.

Example:

Visible problem:
Customers aren't receiving booking confirmations.

Actual root cause:
CRM authentication failure.

Systems inspected:
n8n
WhatsApp workflow
Calendar
CRM
possibly website/database/infrastructure

The business owner should not need to already know which subsystem is broken.

=== END ===


=== BLOCK: REJECTED ===

[DECISION]
Do not make WhatsApp a separate top-level architecture because it runs through n8n.

[DECISION]
Do not add many unrelated integrations purely to make the project look larger.

[DECISION]
Do not start by supporting AWS + Azure + GCP + every platform.

[DECISION]
Do not build a huge frontend before core diagnostics work.

[DECISION]
Do not give the LLM unrestricted production access.

[DECISION]
Do not mark remediation successful without verification.

[DECISION]
Do not rely only on HTTP 200 to determine that a business process works.

[DECISION]
Do not call the AI model for simple deterministic checks that normal code can perform.

Use code for deterministic health checks.

Use AI when reasoning/correlation is required.

=== END ===


=== BLOCK: STYLE OF IMPLEMENTATION ===

[DECISION]

Prefer:
- simple
- explicit
- debuggable
- typed
- tested
- modular
- hackathon-buildable

Avoid:
- unnecessary abstractions
- giant frameworks
- premature distributed architecture
- fake enterprise complexity

Choose boring reliable engineering where possible.

The AI reasoning itself is already the complicated part.

=== END ===


=== BLOCK: CURRENT STATE ===

[FACT]
The project architecture and broad stack have been discussed.

[FACT]
No evidence in the handoff confirms that a functioning repository/application has already been built.

[ASSUMPTION]
Assume implementation is starting from the beginning unless the current repository already contains code.

FIRST ACTION:
Inspect the current repository/folder before creating anything.

If empty:
start Phase 1.

If existing code is present:
inspect it first and report:
- current structure
- what works
- what appears incomplete
- conflicts with this architecture

Do NOT delete useful existing work without explanation.

=== END ===


=== BLOCK: OPEN QUESTIONS ===

[ASSUMPTION]
Exact backend cloud provider is not finalized.

[ASSUMPTION]
Exact currently eligible NVIDIA Nemotron model must be verified.

[ASSUMPTION]
Exact current Nebius SDK/API method should be verified.

[ASSUMPTION]
Exact n8n API details must be verified against current documentation before implementation.

[ASSUMPTION]
Exact Vercel log/event API capabilities must be verified before implementation.

[ASSUMPTION]
Exact Supabase Management API capabilities must be verified before implementation.

UNCLEAR:
Which real client/demo website will eventually be monitored.

UNCLEAR:
Which actual CRM/API will be intentionally broken for the final demo.

UNCLEAR:
Whether the demo n8n instance is cloud-hosted or self-hosted.

These do NOT block Phase 1.

=== END ===


=== BLOCK: NEXT STEP ===

Execute Phase 1 only.

1. Inspect the repository.
2. If necessary initialize it.
3. Create the Python/FastAPI backend foundation.
4. Create configuration handling.
5. Create .gitignore.
6. Create .env.example.
7. Create tests.
8. Implement GET /health.
9. Start the server.
10. Test /health.
11. Run the complete current test suite.
12. Fix every error encountered.

Then STOP.

Report:

FILES CREATED:
...

COMMANDS RUN:
...

TESTS:
...

RESULT:
PASS / FAIL

PROBLEMS:
...

NEXT PROPOSED PHASE:
Nebius/Nemotron integration

Do NOT start the next phase until Phase 1 is working.

=== END ===