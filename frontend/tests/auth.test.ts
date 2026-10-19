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
const platformValues = {
  ...values,
  RELIABILITY_PUBLIC_ORIGIN: undefined,
  VERCEL: "1",
  VERCEL_ENV: "production",
  VERCEL_PROJECT_PRODUCTION_URL: "assigned-project-123.vercel.app",
};
const environmentKeys = [...Object.keys(values), "VERCEL", "VERCEL_ENV", "VERCEL_PROJECT_PRODUCTION_URL"];
beforeEach(() => { Object.assign(process.env, values); });
afterEach(() => { for (const key of environmentKeys) { if (original[key] === undefined) delete process.env[key]; else process.env[key] = original[key]; } globalThis.fetch = originalFetch; });
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

test("external links can reach HTML sign-in while APIs, frames and mutations stay fenced", () => {
  const navigation = { "sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate", "sec-fetch-dest": "document" };
  assert.equal(sameOrigin(request(navigation), false, true), true);
  assert.equal(sameOrigin(request(navigation)), false);
  assert.equal(sameOrigin(request({ ...navigation, origin: "https://dashboard.example", "content-type": "application/json" }), true, true), false);
  assert.equal(sameOrigin(request({ ...navigation, host: "evil.example", "x-forwarded-host": "dashboard.example" }), false, true), false);
  assert.equal(sameOrigin(request({ ...navigation, origin: "https://evil.example" }), false, true), false);
  assert.equal(sameOrigin(request({ ...navigation, "sec-fetch-dest": "iframe" }), false, true), false);
  assert.equal(sameOrigin(request({ ...navigation, "sec-fetch-mode": "cors" }), false, true), false);
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

test("Vercel production metadata selects one canonical project origin", () => {
  assert.equal(deployment(platformValues)?.publicOrigin, "https://assigned-project-123.vercel.app");
});

test("explicit frontend origins take precedence over platform metadata", () => {
  assert.equal(deployment({ ...platformValues, RELIABILITY_PUBLIC_ORIGIN: values.RELIABILITY_PUBLIC_ORIGIN, VERCEL_PROJECT_PRODUCTION_URL: "invalid" })?.publicOrigin, values.RELIABILITY_PUBLIC_ORIGIN);
  assert.throws(() => deployment({ ...platformValues, RELIABILITY_PUBLIC_ORIGIN: "" }));
});

test("platform-origin fallback is unavailable outside a Vercel production deployment", () => {
  for (const changes of [{ VERCEL: undefined }, { VERCEL: "0" }, { VERCEL_ENV: "preview" }, { VERCEL_ENV: "development" }, { VERCEL_ENV: undefined }]) {
    assert.throws(() => deployment({ ...platformValues, ...changes }));
  }
});

test("malformed or unrelated Vercel metadata fails closed", () => {
  for (const value of [undefined, "", "https://project.vercel.app", "*.vercel.app", "evil.example", "project.vercel.app.evil.example", "project.vercel.app:443", "PROJECT.vercel.app", "project.vercel.app/path", "project.vercel.app\n"]) {
    assert.throws(() => deployment({ ...platformValues, VERCEL_PROJECT_PRODUCTION_URL: value }));
  }
});

test("Vercel metadata preserves exact Host and Origin checks", () => {
  Object.assign(process.env, platformValues);
  delete process.env.RELIABILITY_PUBLIC_ORIGIN;
  const host = "assigned-project-123.vercel.app";
  assert.equal(sameOrigin(request({ host, origin: `https://${host}`, "content-type": "application/json" }), true), true);
  assert.equal(sameOrigin(request({ host: "another.vercel.app", "x-forwarded-host": host })), false);
  assert.equal(sameOrigin(request({ host, origin: "https://evil.example", "content-type": "application/json" }), true), false);
});

test("sessions remain bound to the canonical Vercel project origin", () => {
  Object.assign(process.env, platformValues);
  delete process.env.RELIABILITY_PUBLIC_ORIGIN;
  const session = createSession(1000);
  assert.equal(validSession(session, 1001), true);
  process.env.VERCEL_PROJECT_PRODUCTION_URL = "different-project.vercel.app";
  assert.equal(validSession(session, 1001), false);
});
