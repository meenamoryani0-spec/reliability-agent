import { z } from "zod";

export const id = z.string().uuid();
const text = z.string().max(4000);
const stamp = z.string().max(50).refine((s) => Number.isFinite(Date.parse(s)));
const mode = z.enum(["disabled", "fixture", "live"]);
export const status = z.enum(["HEALTHY", "UNHEALTHY", "DEGRADED", "UNKNOWN", "CHECK_FAILED"]);
export const serviceSchema = z.object({
  id, category: text, component: text, synthetic: z.boolean(), created_at: stamp,
});
export const checkSchema = z.object({
  id, service_id: id, category: text, component: text, synthetic: z.boolean(),
  kind: text, status, observed_at: stamp, created_at: stamp,
  payload: z.record(z.string(), z.unknown()),
});
export const incidentSchema = z.object({
  id, service_id: id, detected_check_id: id, category: text, component: text,
  kind: text, title: text, status: z.enum(["OPEN", "INVESTIGATING", "RESOLVED"]),
  severity: z.enum(["warning", "high"]), created_at: stamp, synthetic: z.boolean(),
  observation_count: z.number().int().nonnegative(), first_observed_at: stamp.nullable(),
  last_observed_at: stamp.nullable(), root_cause_verified: z.literal(false),
  root_cause: z.null(), recovery_verified: z.boolean(), business_outcome_verified: z.literal(false),
  resolution_verification_id: id.nullable(), resolution_scope: z.literal("n8n_required_nodes").nullable(),
  resolved_at: stamp.nullable(),
});
export const actionSchema = z.object({
  id, check_id: id, incident_id: id, service_id: id, execution_id: text, workflow_id: text,
  mode: z.enum(["fixture", "live"]), synthetic: z.boolean(),
  state: z.enum(["PENDING", "EXECUTING", "ACCEPTED", "REJECTED", "UNKNOWN"]),
  created_at: stamp, expires_at: stamp, approved_at: stamp.nullable(),
  completed_at: stamp.nullable(), new_execution_id: text.nullable(), reason: text.nullable(),
  recovery_verified: z.boolean(), business_outcome_verified: z.literal(false), risk: text,
});
export const verificationSchema = z.object({
  id, action_id: id, incident_id: id, service_id: id, check_id: id.nullable(),
  result: z.enum(["VERIFIED", "NOT_RECOVERED", "INCONCLUSIVE"]), reason: text,
  original_execution_id: text, new_execution_id: text, workflow_id: text,
  policy: z.record(z.string(), z.unknown()), observed_at: stamp, created_at: stamp,
  scope: z.literal("n8n_required_nodes"), recovery_verified: z.boolean(),
  business_outcome_verified: z.literal(false), root_cause_verified: z.literal(false),
});
export const assessmentSchema = z.object({
  check_id: id, hypothesis: text, recommended_steps: z.array(text).max(5),
  inference_source: z.enum(["scripted_fixture", "nebius"]), root_cause: z.null(),
  root_cause_verified: z.literal(false), created_at: stamp,
});
export const agentSchema = z.object({
  mode, configured: z.boolean(), inference_source: text, model: text,
  deadline_seconds: z.number(), max_model_requests: z.number(), max_tool_calls: z.number(),
});
export const storageSchema = z.object({ mode: text, state: text, automatic_incidents: z.boolean() });
export const actionPolicySchema = z.object({ mode, approval_required: z.literal(true), approval_interface: z.literal("local_operator_cli") });
export const recoveryPolicySchema = z.object({ mode, scope: z.literal("n8n_required_nodes"), http_verification: z.literal(false) });
export const reportSchema = z.object({
  status: z.enum(["COMPLETED", "INCOMPLETE", "CHECK_FAILED", "REJECTED"]),
  reason: text.nullable(), inference_source: z.enum(["disabled", "scripted_fixture", "nebius"]),
  assessment: text, hypothesis: text.nullable(), summary: text,
  cited_evidence_ids: z.array(text).max(8), next_steps: z.array(text).max(5),
  evidence: z.array(z.object({ id: text, result: z.object({
    name: text.nullable(), status: text, reason: text.nullable(), data: z.record(z.string(), z.unknown()).nullable(),
  }) })).max(8),
  model_requests: z.number().int().max(6), tool_calls: z.number().int().max(8),
  evidence_provenance: text, root_cause_verified: z.literal(false),
  business_outcome_verified: z.literal(false), remediation_executed: z.literal(false),
});
export const questionSchema = z.object({ question: z.string().trim().min(1).max(2000)
  .refine((s) => new TextEncoder().encode(s).length <= 3000) }).strict();
export type Service = z.infer<typeof serviceSchema>;
export type Check = z.infer<typeof checkSchema>;
export type Incident = z.infer<typeof incidentSchema>;
export type Action = z.infer<typeof actionSchema>;
export type Verification = z.infer<typeof verificationSchema>;
export type Assessment = z.infer<typeof assessmentSchema>;
export type Report = z.infer<typeof reportSchema>;
export type ReadResult<T> = { data: T | null; error: string | null };
export type Snapshot = {
  fetchedAt: string;
  health: ReadResult<{ status: "ok" }>;
  storage: ReadResult<z.infer<typeof storageSchema>>;
  agent: ReadResult<z.infer<typeof agentSchema>>;
  actionPolicy: ReadResult<z.infer<typeof actionPolicySchema>>;
  recoveryPolicy: ReadResult<z.infer<typeof recoveryPolicySchema>>;
  services: ReadResult<Service[]>;
  checks: ReadResult<Check[]>;
  incidents: ReadResult<Incident[]>;
  actions: ReadResult<Action[]>;
  verifications: ReadResult<Verification[]>;
};
export type IncidentDetail = {
  incident: Incident;
  observations: ReadResult<Check[]>;
  assessments: ReadResult<Assessment[]>;
  proof: ReadResult<Verification> | null;
};
