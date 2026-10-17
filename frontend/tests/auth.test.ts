import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { afterEach, beforeEach, test } from "node:test";
import { allowLogin, authenticated, createSession, SESSION_COOKIE, SESSION_SECONDS, validOperatorKey, validSession } from "../lib/auth";
import { backendOrigin, deployment, sameOrigin } from "../lib/deployment";
import { backendRead, localRequest } from "../lib/backend";
import { z } from "zod";

const original = { ...process.env };
const originalFetch = globalThis.fetch;
const operator = "test_only_operator_" + "x".repeat(32);
const values = {
  RELIABILITY_DASHBOARD_MODE: "production",
  RELIABILITY_PUBLIC_ORIGIN: "https://dashboard.example",
  RELIABILITY_BACKEND_URL: "https://api.example",
  RELIABILITY_BACKEND_TOKEN: "test_only_backend_" + "y".repeat(32),
  RELIABILITY_SESSION_KEY: "test_only_session_" + "z".repeat(32),
  RELIABILITY_OPERATOR_KEY_SHA256: createHash("sha256").update(operator).digest("hex"),
};
beforeEach(() => { Object.assign(process.env, values); });
afterEach(() => { for (const key of Object.keys(values)) { if (original[key] === undefined) delete process.env[key]; else process.env[key] = original[key]; } globalThis.fetch = originalFetch; });
const request = (headers: Record<string, string> = {}) => new Request("http://localhost:3000/api/dashboard", { headers: { host: "dashboard.example", ...headers } });

test("production configuration requires fixed HTTPS origins and independent secrets", () => {
  assert.equal(backendOrigin(values), "https://api.example");
  for (const changes of [{ RELIABILITY_BACKEND_URL: "http://api.example" }, { RELIABILITY_PUBLIC_ORIGIN: "https://dashboard.example/path" }, { RELIABILITY_BACKEND_URL: "https://user:secret@api.example" }, { RELIABILITY_BACKEND_TOKEN: "" }, { RELIABILITY_SESSION_KEY: values.RELIABILITY_BACKEND_TOKEN }, { RELIABILITY_OPERATOR_KEY_SHA256: "weak" }, { RELIABILITY_DASHBOARD_MODE: "unknown" }]) assert.throws(() => deployment({ ...values, ...changes }));
});
test("sessions expire, reject tampering/future timestamps and are audience-bound", () => {
  const token = createSession(1000);
  assert.equal(validSession(token, 1000), true);
  assert.equal(validSession(token, 1000 + SESSION_SECONDS - 1), true);
  assert.equal(validSession(token, 1000 + SESSION_SECONDS), false);
  assert.equal(validSession(token, 999), false);
  assert.equal(validSession(token.slice(0, -1) + "!", 1001), false);
  assert.equal(validSession(token + ".extra", 1001), false);
  process.env.RELIABILITY_PUBLIC_ORIGIN = "https://different.example";
  assert.equal(validSession(token, 1001), false);
});
test("operator or signing-key rotation invalidates existing sessions", () => {
  const session = createSession();
  process.env.RELIABILITY_OPERATOR_KEY_SHA256 = "a".repeat(64);
  assert.equal(validSession(session), false);
  Object.assign(process.env, values);
  process.env.RELIABILITY_SESSION_KEY = "a".repeat(43);
  assert.equal(validSession(session), false);
});
test("dashboard requires one signed cookie and exact configured Host", () => {
  const cookie = `${SESSION_COOKIE}=${createSession()}`;
  assert.equal(authenticated(request()), false);
  assert.equal(localRequest(request({ cookie })), true);
  assert.equal(localRequest(request({ cookie, host: "evil.example", "x-forwarded-host": "dashboard.example" })), false);
  assert.equal(authenticated(request({ cookie: `${cookie}; ${cookie}` })), false);
  assert.equal(localRequest(request({ authorization: `Bearer ${values.RELIABILITY_BACKEND_TOKEN}` })), false);
  assert.equal(sameOrigin(request({ origin: "https://evil.example" }), true), false);
  assert.equal(sameOrigin(request({ origin: "https://dashboard.example", "content-type": "application/json" }), true), true);
});
test("BFF sends the service token only on its fixed server connection", async () => {
  globalThis.fetch = async (input, options) => {
    assert.equal(String(input), "https://api.example/health");
    const headers = new Headers(options?.headers);
    assert.equal(headers.get("authorization"), `Bearer ${values.RELIABILITY_BACKEND_TOKEN}`);
    assert.equal(headers.has("cookie"), false);
    assert.equal(headers.has("origin"), false);
    return Response.json({ status: "ok", token: "must_be_stripped" });
  };
  assert.deepEqual(await backendRead("/health", z.object({ status: z.literal("ok") })), { data: { status: "ok" }, error: null });
});
test("operator login accepts only the generated key shape and exact digest", () => {
  assert.equal(validOperatorKey(operator), true);
  for (const input of ["wrong", operator + "x", { key: operator }, null, "a".repeat(200)]) assert.equal(validOperatorKey(input), false);
});
test("per-instance login burst refills slowly", () => {
  const now = Date.now() + 60_000;
  for (let index = 0; index < 10; index++) assert.equal(allowLogin(now), true);
  assert.equal(allowLogin(now), false);
  assert.equal(allowLogin(now + 59_000), false);
  assert.equal(allowLogin(now + 60_000), true);
});
