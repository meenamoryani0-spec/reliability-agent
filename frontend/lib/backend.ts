import "server-only";
import { authenticated } from "./auth";
import { backendOrigin, deployment, sameOrigin } from "./deployment";
import { z } from "zod";
import {
  actionPolicySchema, actionSchema, agentSchema, assessmentSchema, checkSchema, id,
  incidentSchema, recoveryPolicySchema, reportSchema, serviceSchema, storageSchema,
  verificationSchema, type IncidentDetail, type ReadResult, type Snapshot,
} from "./contracts";

const MAX_RESPONSE_BYTES = 1_048_576;
export const backendBase = backendOrigin;

export function localRequest(request: Request, mutation = false): boolean {
  return sameOrigin(request, mutation) && authenticated(request);
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

export async function backendRead<T>(path: string, schema: z.ZodType<T>, options?: Record<string, unknown>, timeoutMs?: number): Promise<ReadResult<T>> {
  try {
    const base = backendBase();
    const config = deployment();
    const headers: Record<string, string> = { Accept: "application/json" };
    if (options) headers["Content-Type"] = "application/json";
    if (config) headers.Authorization = `Bearer ${config.token}`;
    const response = await fetch(`${base}${path}`, {
      method: options ? "POST" : "GET", cache: "no-store", redirect: "error",
      signal: AbortSignal.timeout(timeoutMs ?? (options ? 125_000 : 8000)),
      headers,
      body: options ? JSON.stringify(options) : undefined,
    });
    if (!response.ok) {
      await response.body?.cancel();
      return { data: null, error: response.status === 503 ? "unavailable" : response.status === 404 ? "access_unavailable" : response.status === 409 ? "busy_or_limit" : response.status === 422 ? "invalid_input" : "backend_error" };
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
