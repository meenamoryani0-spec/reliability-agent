import { Dashboard } from "@/components/dashboard";
import { cookies, headers } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { SESSION_COOKIE, validSession } from "@/lib/auth";
import { deployment, sameOrigin } from "@/lib/deployment";
export const dynamic = "force-dynamic";
export default async function DashboardPage() {
  const config = deployment();
  if (config) {
    const incoming = await headers();
    if (!sameOrigin(new Request(config.publicOrigin, { headers: incoming }), false, true)) notFound();
    if (!validSession((await cookies()).get(SESSION_COOKIE)?.value)) redirect("/login");
  }
  return <Dashboard deployed={!!config} />;
}
