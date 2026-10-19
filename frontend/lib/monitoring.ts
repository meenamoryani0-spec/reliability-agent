import { z } from "zod";
import { checkSchema, status } from "./contracts";

export const targetSchema = z.object({
  id: z.string().regex(/^[a-z][a-z0-9-]{0,31}$/), url: z.string().max(2048),
  expected_statuses: z.array(z.number().int().min(200).max(299)).max(10),
  latency_warning_ms: z.number().int().min(1).max(60000),
});
const providerMode = z.enum(["disabled", "fixture", "live"]);
const integrationSchema = z.object({ mode: providerMode, configured: z.boolean(), synthetic: z.boolean() });
export const infrastructureId = z.enum(["vercel-deployment", "vercel-events", "supabase-project", "supabase-health", "postgres"]);
export const monitoringSchema = z.object({
  websites: z.object({ targets: z.array(targetSchema).max(25), error: z.string().nullable() }),
  n8n: integrationSchema,
  n8n_reports: z.object({ enabled: z.boolean(), workflow_count: z.number().int().min(0).max(25),
    coverage: z.literal("received_failure_notifications_only") }).optional(),
  infrastructure: z.object({ mode: providerMode, synthetic: z.boolean(), checks: z.array(z.object({ id: infrastructureId, configured: z.boolean() })).max(5) }),
  automatic_monitoring: z.literal(false),
});
export const operatorRequestSchema = z.discriminatedUnion("action", [
  z.object({ action: z.literal("register_website"), url: z.string().trim().min(1).max(2048) }).strict(),
  z.object({ action: z.literal("check_website"), target_id: targetSchema.shape.id }).strict(),
  z.object({ action: z.literal("n8n_workflows") }).strict(),
  z.object({ action: z.literal("n8n_reports") }).strict(),
  z.object({ action: z.literal("n8n_failed"), workflow_id: z.string().regex(/^[A-Za-z0-9_-]{1,64}$/).optional() }).strict(),
  z.object({ action: z.literal("n8n_execution"), execution_id: z.string().regex(/^[1-9][0-9]{0,18}$/) }).strict(),
  z.object({ action: z.literal("infrastructure"), check_id: infrastructureId }).strict(),
]);
export const websiteResultSchema = z.object({
  results: z.array(z.object({
    check: z.object({ component: z.string(), check_type: z.enum(["http", "dns", "ssl"]), status,
      summary: z.string().max(4000), evidence: z.record(z.string(), z.unknown()),
      latency_ms: z.number().nullable(), checked_at: z.string(), healthy: z.boolean().nullable() }),
    history: z.object({ status: z.enum(["saved", "unavailable", "disabled", "not_applicable"]), check_id: z.string().nullable() }),
  })).length(3), automatic_monitoring: z.literal(false),
});
export const n8nResultSchema = z.object({
  operation: z.enum(["workflows", "failed_executions", "execution"]), status: z.enum(["OK", "CHECK_FAILED"]),
  synthetic: z.boolean(), reason: z.string().nullable(), next_cursor: z.string().nullable(),
  workflows: z.array(z.object({ id: z.string(), active: z.boolean() })).max(50),
  executions: z.array(z.object({ id: z.string(), workflow_id: z.string(), execution_state: z.string(),
    started_at: z.string().nullable(), stopped_at: z.string().nullable() })).max(50),
  execution: z.object({ id: z.string(), workflow_id: z.string(), status, summary: z.string(),
    data_availability: z.string(), failures: z.array(z.record(z.string(), z.unknown())).max(25),
    observed_nodes: z.array(z.record(z.string(), z.unknown())).max(100),
    root_cause_verified: z.literal(false), business_outcome_verified: z.literal(false),
  }).nullable(), checked_at: z.string(),
});
export const infrastructureResultSchema = z.object({
  component: infrastructureId, status, summary: z.string(), synthetic: z.boolean(),
  reason: z.string().nullable(), evidence: z.record(z.string(), z.unknown()),
  root_cause_verified: z.literal(false), business_outcome_verified: z.literal(false), checked_at: z.string(),
});
export type Monitoring = z.infer<typeof monitoringSchema>;
export type OperatorRequest = z.infer<typeof operatorRequestSchema>;
export type WebsiteResults = z.infer<typeof websiteResultSchema>;
export type N8nResults = z.infer<typeof n8nResultSchema>;

export const failureReportsSchema = z.object({ reports: z.array(checkSchema).max(25),
  coverage: z.literal("received_failure_notifications_only"), absence_proves_health: z.literal(false) });
export type FailureReports = z.infer<typeof failureReportsSchema>;
