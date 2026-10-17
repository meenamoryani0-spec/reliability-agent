import assert from "node:assert/strict";
import { test } from "node:test";
import { actionLabel, age, isStale, latestChecks, matches } from "../lib/presentation";
import type { Action, Check } from "../lib/contracts";

const time = Date.parse("2026-10-17T12:00:00Z");
const check = (service: string, kind: string, seconds: number, state = "HEALTHY") => ({
  service_id: service, kind, observed_at: new Date(time + seconds * 1000).toISOString(), status: state,
}) as Check;
test("latest signals use observation time, retain check kind and source identity", () => {
  const old = check("live-service", "http", -100);
  const fresh = check("live-service", "http", -10, "UNHEALTHY");
  const dns = check("live-service", "dns", -5);
  const synthetic = check("synthetic-service", "http", -3);
  assert.deepEqual(latestChecks([fresh, old, dns, synthetic]), [fresh, dns, synthetic]);
});
test("stale and future observations do not count as recent healthy signals", () => {
  assert.equal(isStale(check("s", "http", -301), time), true);
  assert.equal(isStale(check("s", "http", 6), time), true);
  assert.equal(isStale(check("s", "http", -30), time), false);
  assert.equal(age(new Date(time + 60000).toISOString(), time), "Clock ahead");
});
test("approval expiry is derived from the immutable pending record", () => {
  assert.equal(actionLabel({ state: "PENDING", expires_at: new Date(time - 1).toISOString() } as Action, time), "Approval expired");
  assert.equal(actionLabel({ state: "PENDING", expires_at: new Date(time + 1000).toISOString() } as Action, time), "Awaiting operator");
  assert.equal(actionLabel({ state: "ACCEPTED" } as Action, time), "Retry accepted");
  assert.equal(actionLabel({ state: "UNKNOWN" } as Action, time), "Dispatch uncertain");
});
test("search matches text without treating it as a regular expression", () => {
  assert.equal(matches(" BOOKING ", "workflow:booking"), true);
  assert.equal(matches(".*", "workflow:booking"), false);
});
