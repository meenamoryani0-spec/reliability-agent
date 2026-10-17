import { boundedJson, investigate, localRequest } from "@/lib/backend";
import { questionSchema } from "@/lib/contracts";
export const maxDuration = 130;
export async function POST(request: Request) {
  if (!localRequest(request, true)) return Response.json({ error: "same_origin_json_required" }, { status: 403 });
  try {
    const parsed = questionSchema.safeParse(await boundedJson(new Response(request.body, { headers: request.headers }), 4096));
    if (!parsed.success) return Response.json({ error: "invalid_question" }, { status: 422 });
    const result = await investigate(parsed.data.question);
    return Response.json(result, { status: result.data ? 200 : 503, headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ error: "invalid_request" }, { status: 400 }); }
}
