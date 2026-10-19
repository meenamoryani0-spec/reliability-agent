import { backendRead, boundedJson, localRequest } from "@/lib/backend";
import { failureReportsSchema, infrastructureResultSchema, monitoringSchema, n8nResultSchema, operatorRequestSchema, targetSchema, websiteResultSchema } from "@/lib/monitoring";

export const dynamic = "force-dynamic";
export const maxDuration = 60;
const headers = { "Cache-Control": "no-store" };

export async function GET(request: Request) {
  if (!localRequest(request)) return Response.json({ error: "access_required" }, { status: 403 });
  const result = await backendRead("/monitoring", monitoringSchema);
  return Response.json(result, { status: result.data ? 200 : 503, headers });
}

export async function POST(request: Request) {
  if (!localRequest(request, true)) return Response.json({ error: "same_origin_json_required" }, { status: 403 });
  try {
    const parsed = operatorRequestSchema.safeParse(await boundedJson(new Response(request.body, { headers: request.headers }), 4096));
    if (!parsed.success) return Response.json({ error: "invalid_monitoring_request" }, { status: 422 });
    const command = parsed.data;
    const result = command.action === "register_website"
      ? await backendRead("/monitoring/websites", targetSchema, { url: command.url }, 10_000)
      : command.action === "check_website"
      ? await backendRead(`/monitoring/websites/${command.target_id}/checks`, websiteResultSchema, {}, 50_000)
      : command.action === "n8n_workflows"
      ? await backendRead("/n8n/workflows?limit=25", n8nResultSchema, undefined, 35_000)
      : command.action === "n8n_reports"
      ? await backendRead("/monitoring/n8n/reports", failureReportsSchema)
      : command.action === "n8n_failed"
      ? await backendRead(`/n8n/executions/failed?limit=25${command.workflow_id ? `&workflow_id=${command.workflow_id}` : ""}`, n8nResultSchema, undefined, 35_000)
      : command.action === "n8n_execution"
      ? await backendRead(`/n8n/executions/${command.execution_id}`, n8nResultSchema, undefined, 35_000)
      : await backendRead(`/checks/infrastructure/${command.check_id}`, infrastructureResultSchema, {}, 45_000);
    return Response.json(result, { status: result.data ? 200 : 503, headers });
  } catch { return Response.json({ error: "invalid_request" }, { status: 400, headers }); }
}
