import "server-only";

type Environment = Record<string, string | undefined>;
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);
export function production(environment: Environment = process.env): boolean {
  const mode = environment.RELIABILITY_DASHBOARD_MODE ?? "local";
  if (mode !== "local" && mode !== "production") throw new Error("invalid_deployment_mode");
  if (environment.VERCEL === "1" && mode !== "production") throw new Error("production_configuration_required");
  return mode === "production";
}

function origin(value: string | undefined, https: boolean): URL {
  const url = new URL(value ?? "");
  if (url.protocol !== (https ? "https:" : "http:") || url.username || url.password
    || url.pathname !== "/" || url.search || url.hash) throw new Error("invalid_origin");
  return url;
}

export function deployment(environment: Environment = process.env) {
  if (!production(environment)) return null;
  const publicOrigin = origin(environment.RELIABILITY_PUBLIC_ORIGIN, true).origin;
  const backend = origin(environment.RELIABILITY_BACKEND_URL, true).origin;
  const token = environment.RELIABILITY_BACKEND_TOKEN ?? "";
  const key = environment.RELIABILITY_SESSION_KEY ?? "";
  const digest = environment.RELIABILITY_OPERATOR_KEY_SHA256 ?? "";
  if (!/^[A-Za-z0-9_-]{43,128}$/.test(token) || !/^[A-Za-z0-9_-]{43,128}$/.test(key)
    || !/^[a-f0-9]{64}$/.test(digest) || token === key || publicOrigin === backend) throw new Error("invalid_access_configuration");
  return { publicOrigin, backend, token, key, digest };
}

export function backendOrigin(environment: Environment = process.env): string {
  const config = deployment(environment);
  if (config) return config.backend;
  const url = origin(environment.RELIABILITY_BACKEND_URL ?? "http://127.0.0.1:8000", false);
  if (!LOOPBACK.has(url.hostname)) throw new Error("invalid_backend_configuration");
  return url.origin;
}

// Authority comes from exact operator configuration/Host, never X-Forwarded-*.
export function sameOrigin(request: Request, mutation = false): boolean {
  try {
    const config = deployment();
    const host = request.headers.get("host");
    if (!host) return false;
    const target = new URL(`${config ? "https" : "http"}://${host}`);
    if (target.host !== host || target.pathname !== "/" || target.username || target.password) return false;
    if (config ? target.origin !== config.publicOrigin
      : !LOOPBACK.has(target.hostname) || !LOOPBACK.has(new URL(request.url).hostname)) return false;
    const origin = request.headers.get("origin");
    if (origin && origin !== target.origin) return false;
    if (mutation && (origin !== target.origin || request.headers.get("content-type")?.split(";")[0].trim() !== "application/json")) return false;
    return request.headers.get("sec-fetch-site") !== "cross-site";
  } catch { return false; }
}
