import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { GET, POST } from "../app/api/monitoring/route";
import { monitoringSchema, operatorRequestSchema } from "../lib/monitoring";

const originalFetch = globalThis.fetch;

test("monitoring accepts bounded scheduler activity without claiming website health", () => {
  const data = {
    websites: { targets: [], error: null }, n8n: { mode: "disabled", configured: false, synthetic: false },
    infrastructure: { mode: "disabled", synthetic: false, checks: [] }, automatic_monitoring: true,
    website_schedule: { enabled: true, interval_seconds: 300, state: "waiting", last_started_at: null,
      last_finished_at: null, last_outcome: "storage_unavailable", last_checks_saved: 0,
      cycles_started: 1, coverage: "registered_websites_while_backend_running" },
  };
  assert.equal(monitoringSchema.safeParse(data).success, true);
  assert.equal(monitoringSchema.safeParse({ ...data, website_schedule: { ...data.website_schedule, interval_seconds: 0 } }).success, false);
  assert.equal(monitoringSchema.safeParse({ ...data, website_schedule: { ...data.website_schedule, last_checks_saved: 76 } }).success, false);
  assert.equal(monitoringSchema.safeParse({ ...data, website_schedule: undefined, automatic_monitoring: false }).success, true);
});
afterEach(() => { globalThis.fetch = originalFetch; });
const request = (body: unknown, origin = "http://localhost:3000") => new Request("http://localhost:3000/api/monitoring", {
  method: "POST", headers: { Host: "localhost:3000", Origin: origin, "Content-Type": "application/json" }, body: JSON.stringify(body),
});

test("monitoring rejects unauthenticated hosts, cross-origin mutations and arbitrary tools before fetch", async () => {
  globalThis.fetch = async () => { throw new Error("must not reach backend"); };
  assert.equal((await GET(new Request("http://evil.test/api/monitoring", { headers: { host: "evil.test" } }))).status, 403);
  assert.equal((await POST(request({ action: "check_website", target_id: "demo" }, "http://evil.test"))).status, 403);
  for (const command of [{ action: "shell", command: "x" }, { action: "check_website", url: "http://localhost" }, { action: "n8n_execution", execution_id: "../../actions" }, { action: "infrastructure", check_id: "arbitrary" }, { action: "register_website", url: "https://example.com", token: "private" }]) {
    assert.equal((await POST(request(command))).status, 422);
  }
});

test("website registration reaches only the fixed backend with the bounded public URL field", async () => {
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "http://127.0.0.1:8000/monitoring/websites");
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(String(init?.body)), { url: "https://example.com" });
    return Response.json({ id: "demo", url: "https://example.com/", expected_statuses: [200], latency_warning_ms: 2000, extra: "stripped" });
  };
  const response = await POST(request({ action: "register_website", url: "https://example.com" }));
  assert.equal(response.status, 200);
  assert.equal((await response.json()).data.extra, undefined);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
});

test("read tools cannot be redirected to arbitrary providers or remediation routes", () => {
  for (const command of [{ action: "n8n_failed", workflow_id: "a/b" }, { action: "n8n_workflows", url: "https://evil.test" }, { action: "retry_n8n_execution", execution_id: "123" }, { action: "register_website", url: "x".repeat(2049) }]) {
    assert.equal(operatorRequestSchema.safeParse(command).success, false);
  }
  assert.equal(operatorRequestSchema.safeParse({ action: "n8n_execution", execution_id: "123" }).success, true);
});

test("received n8n reports use a fixed authenticated read and retain limited coverage", async () => {
  globalThis.fetch = async (input, init) => {
    assert.equal(String(input), "http://127.0.0.1:8000/monitoring/n8n/reports");
    assert.equal(init?.method, "GET");
    return Response.json({ reports: [], coverage: "received_failure_notifications_only", absence_proves_health: false });
  };
  const response = await POST(request({ action: "n8n_reports" }));
  assert.equal(response.status, 200);
  assert.equal((await response.json()).data.absence_proves_health, false);
  assert.equal((await POST(request({ action: "n8n_reports", token: "secret" }))).status, 422);
});
