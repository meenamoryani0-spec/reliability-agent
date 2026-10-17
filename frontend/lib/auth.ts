import "server-only";
import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { deployment } from "./deployment";

export const SESSION_COOKIE = "__Host-reliability-session";
export const SESSION_SECONDS = 8 * 60 * 60;
function signature(payload: string, key: string) {
  return createHmac("sha256", key).update(`reliability-session-v1.${payload}`).digest("base64url");
}
export function createSession(now = Math.floor(Date.now() / 1000)): string {
  const config = deployment();
  if (!config) throw new Error("authentication_disabled");
  const payload = Buffer.from(JSON.stringify({ iat: now, exp: now + SESSION_SECONDS, nonce: randomBytes(24).toString("base64url"), aud: config.publicOrigin, operator: config.digest })).toString("base64url");
  return `${payload}.${signature(payload, config.key)}`;
}
export function validSession(value: string | undefined, now = Math.floor(Date.now() / 1000)): boolean {
  try {
    const config = deployment();
    if (!config || !value || value.length > 1024 || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}$/.test(value)) return false;
    const [payload, mac] = value.split(".");
    const expected = signature(payload, config.key);
    if (!timingSafeEqual(Buffer.from(mac), Buffer.from(expected))) return false;
    const session = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    return Number.isSafeInteger(session.iat) && Number.isSafeInteger(session.exp)
      && session.iat <= now && session.exp > now && session.exp - session.iat === SESSION_SECONDS
      && session.aud === config.publicOrigin && session.operator === config.digest
      && typeof session.nonce === "string" && /^[A-Za-z0-9_-]{32}$/.test(session.nonce);
  } catch { return false; }
}
export function authenticated(request: Request): boolean {
  try {
    if (!deployment()) return true;
    const cookies = (request.headers.get("cookie") ?? "").split(";").map((part) => part.trim()).filter((part) => part.startsWith(`${SESSION_COOKIE}=`));
    return cookies.length === 1 && validSession(cookies[0].slice(SESSION_COOKIE.length + 1));
  } catch { return false; }
}
export function validOperatorKey(value: unknown): boolean {
  const config = deployment();
  if (!config || typeof value !== "string" || !/^[A-Za-z0-9_-]{43,128}$/.test(value)) return false;
  return timingSafeEqual(createHash("sha256").update(value).digest(), Buffer.from(config.digest, "hex"));
}

// A bounded per-instance burst budget. The hosting edge must enforce a shared
// login limit when using multiple/serverless instances; this is not an IP identity.
let loginBudget = 10;
let loginUpdated = Date.now();
export function allowLogin(now = Date.now()): boolean {
  loginBudget = Math.min(10, loginBudget + Math.max(0, now - loginUpdated) / 60_000);
  loginUpdated = now;
  if (loginBudget < 1) return false;
  loginBudget -= 1;
  return true;
}
