import { localRequest, snapshot } from "@/lib/backend";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  if (!localRequest(request)) return Response.json({ error: "local_access_required" }, { status: 403 });
  return Response.json(await snapshot(), { headers: { "Cache-Control": "no-store" } });
}
