import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { z } from "zod";
import { backendBase, backendRead, boundedJson, incidentDetail, localRequest, snapshot } from "../lib/backend";
import { questionSchema, reportSchema } from "../lib/contracts";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const json = (value: unknown, status = 200) => Response.json(value, { status });
test("only fixed local backend origins are accepted", () => {
  for (const url of ["http://127.0.0.1:8123", "http://localhost:8000", "http://[::1]:8000"]) {
    assert.equal(backendBase({ RELIABILITY_BACKEND_URL: url }), url);
  }
  for (const url of ["https://example.com", "http://127.0.0.1.evil.test", "http://user:secret@localhost:8000", "http://localhost:8000/path", "http://localhost:8000/?url=secret", "http://localhost:8000/#x", "https://localhost:8000"]) {
    assert.throws(() => backendBase({ RELIABILITY_BACKEND_URL: url }));
  }
  assert.throws(() => backendBase({ RELIABILITY_DASHBOARD_MODE: "production" }));
});
test("mutations need a matching explicit origin and JSON", () => {
  const request = (headers: Record<string, string>) => new Request("http://localhost:3000/api/investigations", { headers: { host: "localhost:3000", ...headers } });
  assert.equal(localRequest(request({ origin: "http://localhost:3000", "content-type": "application/json" }), true), true);
  for (const headers of [{}, { origin: "http://evil.test", "content-type": "application/json" }, { origin: "http://localhost:3000", "content-type": "text/plain" }, { origin: "http://localhost:3000", "content-type": "application/json", "sec-fetch-site": "cross-site" }]) {
    assert.equal(localRequest(request(headers as Record<string, string>), true), false);
  }
  assert.equal(localRequest(request({ host: "evil.test" })), false);
  assert.equal(localRequest(new Request("http://evil.test/api/dashboard", { headers: { host: "evil.test" } })), false);
  assert.equal(localRequest(new Request("http://localhost:3000/api/dashboard", { headers: { host: "127.0.0.1:3000" } })), true);
  assert.equal(localRequest(new Request("http://localhost:3000/api/investigations", { headers: { host: "127.0.0.1:3000", origin: "http://127.0.0.1:3000", "content-type": "application/json" } }), true), true);
});
test("streaming JSON is bounded without trusting Content-Length", async () => {
  const stream = new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode('{"data":"')); c.enqueue(new TextEncoder().encode("a".repeat(200))); c.close(); } });
  await assert.rejects(boundedJson(new Response(stream, { headers: { "Content-Type": "application/json" } }), 100));
  await assert.rejects(boundedJson(new Response("{}", { headers: { "Content-Type": "text/html" } })));
  await assert.rejects(boundedJson(new Response("{}", { headers: { "Content-Type": "application/json", "Content-Length": "9000" } }), 100));
  assert.deepEqual(await boundedJson(json({ ok: true })), { ok: true });
});
test("upstream errors never return raw provider or network messages", async () => {
  globalThis.fetch = async () => { throw new Error("PRIVATE_CREDENTIAL_DO_NOT_RETURN"); };
  assert.deepEqual(await backendRead("/health", z.object({ status: z.literal("ok") })), { data: null, error: "connection_unavailable" });
  globalThis.fetch = async () => json({ detail: "PRIVATE_CREDENTIAL_DO_NOT_RETURN" }, 503);
  assert.deepEqual(await backendRead("/health", z.object({ status: z.literal("ok") })), { data: null, error: "unavailable" });
});
test("malformed and incompatible backend responses fail closed", async () => {
  globalThis.fetch = async () => json({ status: "healthy", secret: "private" });
  assert.deepEqual(await backendRead("/health", z.object({ status: z.literal("ok") })), { data: null, error: "invalid_response" });
});
test("unrelated history failures do not change backend liveness", async () => {
  const paths: string[] = [];
  globalThis.fetch = async (input, options) => {
    const path = new URL(String(input)).pathname; paths.push(path);
    assert.equal(options?.cache, "no-store"); assert.equal(options?.redirect, "error");
    if (path === "/health") return json({ status: "ok", private: "stripped" });
    if (path === "/storage") return json({ mode: "disabled", state: "disabled", automatic_incidents: false });
    if (path.startsWith("/history/")) return json({ detail: "storage_disabled" }, 503);
    return json({}, 404);
  };
  const result = await snapshot();
  assert.deepEqual(result.health.data, { status: "ok" });
  assert.equal(result.checks.data, null); assert.equal(result.incidents.data, null);
  assert.equal(result.storage.data?.state, "disabled");
  assert.equal(paths.length, 10); assert.equal(paths.some((p) => p.startsWith("/checks/")), false);
});
test("invalid incident identifiers never reach the backend", async () => {
  globalThis.fetch = async () => { throw new Error("must not fetch"); };
  assert.deepEqual(await incidentDetail("../../actions/execute"), { data: null, error: "invalid_identifier" });
});
test("questions have strict keys, bounded text and UTF-8 length", () => {
  assert.equal(questionSchema.safeParse({ question: "  Why did this fail?  " }).data?.question, "Why did this fail?");
  for (const value of [{ question: " " }, { question: "a".repeat(2001) }, { question: "界".repeat(1001) }, { question: "Why?", url: "http://evil.test" }]) assert.equal(questionSchema.safeParse(value).success, false);
});
test("investigation reports cannot claim root cause, customer success or remediation", () => {
  const report = { status: "COMPLETED", reason: null, inference_source: "scripted_fixture", assessment: "observed_failure", hypothesis: "authentication_rejection", summary: "Authentication rejection observed; cause unknown.", cited_evidence_ids: ["e1"], next_steps: ["inspect_authentication_configuration"], evidence: [{ id: "e1", result: { name: "get_n8n_execution", status: "OK", reason: null, data: {} } }], model_requests: 3, tool_calls: 4, evidence_provenance: "synthetic_only", root_cause_verified: false, business_outcome_verified: false, remediation_executed: false };
  assert.equal(reportSchema.safeParse(report).success, true);
  for (const field of ["root_cause_verified", "business_outcome_verified", "remediation_executed"]) assert.equal(reportSchema.safeParse({ ...report, [field]: true }).success, false);
});
