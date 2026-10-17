import "server-only";
import { z } from "zod";
import {
  actionPolicySchema, actionSchema, agentSchema, assessmentSchema, checkSchema, id,
  incidentSchema, recoveryPolicySchema, reportSchema, serviceSchema, storageSchema,
  verificationSchema, type IncidentDetail, type ReadResult, type Snapshot,
} from "./contracts";

const MAX_RESPONSE_BYTES = 1_048_576;
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);

export function backendBase(environment: Record<string, string | undefined> = process.env): string {
  if ((environment.RELIABILITY_DASHBOARD_MODE ?? "local") !== "local") throw new Error("local_only");
  const url = new URL(environment.RELIABILITY_BACKEND_URL ?? "http://127.0.0.1:8000");
  if (!LOOPBACK.has(url.hostname) || url.protocol !== "http:" || url.username || url.password
    || url.pathname !== "/" || url.search || url.hash) throw new Error("invalid_backend_configuration");
  return url.origin;
}

export function localRequest(request: Request, mutation = false): boolean {
  try {
    backendBase();
    const host = request.headers.get("host");
    if (!host) return false;
    const target = new URL(`http://${host}`);
    const internal = new URL(request.url);
    if (!LOOPBACK.has(target.hostname) || target.host !== host || target.pathname !== "/"
      || target.username || target.password || !LOOPBACK.has(internal.hostname)) return false;
    const origin = request.headers.get("origin");
    if (origin && origin !== target.origin) return false;
    if (mutation && (origin !== target.origin || request.headers.get("content-type")?.split(";")[0].trim() !== "application/json")) return false;
    return request.headers.get("sec-fetch-site") !== "cross-site";
  } catch { return false; }
}

export async function boundedJson(response: Response, maximum = MAX_RESPONSE_BYTES): Promise<unknown> {
  if (!response.headers.get("content-type")?.includes("application/json")) throw new Error("invalid_response");
  if (Number(response.headers.get("content-length")) > maximum) throw new Error("response_too_large");
  if (!response.body) throw new Error("invalid_response");
  const reader = response.body.getReader();
  const parts: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximum) throw new Error("response_too_large");
      parts.push(value);
    }
    const joined = new Uint8Array(size);
    let position = 0;
    for (const part of parts) { joined.set(part, position); position += part.byteLength; }
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(joined));
  } finally { await reader.cancel().catch(() => {}); }
}

export async function backendRead<T>(path: string, schema: z.ZodType<T>, options?: { question: string }): Promise<ReadResult<T>> {
  try {
    const base = backendBase();
    const response = await fetch(`${base}${path}`, {
      method: options ? "POST" : "GET", cache: "no-store", redirect: "error",
      signal: AbortSignal.timeout(options ? 125_000 : 8000),
      headers: options ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
      body: options ? JSON.stringify(options) : undefined,
    });
    if (!response.ok) {
      await response.body?.cancel();
      return { data: null, error: response.status === 503 ? "unavailable" : response.status === 404 ? "access_unavailable" : "backend_error" };
    }
    const parsed = schema.safeParse(await boundedJson(response));
    return parsed.success ? { data: parsed.data, error: null } : { data: null, error: "invalid_response" };
  } catch { return { data: null, error: "connection_unavailable" }; }
}

export async function snapshot(): Promise<Snapshot> {
  const [health, storage, agent, actionPolicy, recoveryPolicy, services, checks, incidents, actions, verifications] = await Promise.all([
    backendRead("/health", z.object({ status: z.literal("ok") })),
    backendRead("/storage", storageSchema), backendRead("/agent", agentSchema),
    backendRead("/actions", actionPolicySchema), backendRead("/recovery", recoveryPolicySchema),
    backendRead("/history/services?limit=100", z.array(serviceSchema).max(100)),
    backendRead("/history/checks?limit=100", z.array(checkSchema).max(100)),
    backendRead("/history/incidents?limit=100", z.array(incidentSchema).max(100)),
    backendRead("/history/actions?limit=100", z.array(actionSchema).max(100)),
    backendRead("/history/verifications?limit=100", z.array(verificationSchema).max(100)),
  ]);
  return { fetchedAt: new Date().toISOString(), health, storage, agent, actionPolicy, recoveryPolicy, services, checks, incidents, actions, verifications };
}

export async function incidentDetail(identifier: string): Promise<ReadResult<IncidentDetail>> {
  if (!id.safeParse(identifier).success) return { data: null, error: "invalid_identifier" };
  const incident = await backendRead(`/history/incidents/${identifier}`, incidentSchema);
  if (!incident.data) return { data: null, error: incident.error };
  const [observations, assessments, proof] = await Promise.all([
    backendRead(`/history/incidents/${identifier}/observations?limit=100`, z.array(checkSchema).max(100)),
    backendRead(`/history/incidents/${identifier}/assessments?limit=100`, z.array(assessmentSchema).max(100)),
    incident.data.resolution_verification_id
      ? backendRead(`/history/verifications/${incident.data.resolution_verification_id}`, verificationSchema) : null,
  ]);
  return { data: { incident: incident.data, observations, assessments, proof }, error: null };
}

export const investigate = (question: string) => backendRead("/investigations", reportSchema, { question });
