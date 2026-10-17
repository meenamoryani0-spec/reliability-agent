import { incidentDetail, localRequest } from "@/lib/backend";
export const dynamic = "force-dynamic";
export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  if (!localRequest(request)) return Response.json({ error: "local_access_required" }, { status: 403 });
  const result = await incidentDetail((await context.params).id);
  return Response.json(result, { status: result.data ? 200 : 400, headers: { "Cache-Control": "no-store" } });
}
