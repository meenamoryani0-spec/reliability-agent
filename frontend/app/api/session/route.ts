import { NextResponse } from "next/server";
import { allowLogin, createSession, SESSION_COOKIE, SESSION_SECONDS, validOperatorKey } from "@/lib/auth";
import { boundedJson } from "@/lib/backend";
import { deployment, sameOrigin } from "@/lib/deployment";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "no-store" };
export async function POST(request: Request) {
  if (!sameOrigin(request, true)) return NextResponse.json({ error: "access_denied" }, { status: 403, headers });
  if (!deployment()) return NextResponse.json({ error: "local_mode" }, { status: 404, headers });
  if (!allowLogin()) return NextResponse.json({ error: "try_later" }, { status: 429, headers: { ...headers, "Retry-After": "60" } });
  try {
    const body = await boundedJson(new Response(request.body, { headers: request.headers }), 512);
    if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).length !== 1
      || !("key" in body) || !validOperatorKey(body.key)) return NextResponse.json({ error: "invalid_key" }, { status: 401, headers });
    const response = NextResponse.json({ ok: true }, { headers });
    response.cookies.set(SESSION_COOKIE, createSession(), { httpOnly: true, secure: true, sameSite: "strict", path: "/", maxAge: SESSION_SECONDS });
    return response;
  } catch { return NextResponse.json({ error: "invalid_request" }, { status: 400, headers }); }
}
export async function DELETE(request: Request) {
  if (!sameOrigin(request, true)) return NextResponse.json({ error: "access_denied" }, { status: 403, headers });
  const response = NextResponse.json({ ok: true }, { headers });
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, secure: true, sameSite: "strict", path: "/", maxAge: 0 });
  return response;
}
