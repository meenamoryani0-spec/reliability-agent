import Link from "next/link";
import { cookies, headers } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { TargetIcon } from "@radix-ui/react-icons";
import { OperatorLogin } from "@/components/operator-login";
import { SESSION_COOKIE, validSession } from "@/lib/auth";
import { deployment, sameOrigin } from "@/lib/deployment";
export const dynamic = "force-dynamic";
export default async function LoginPage() {
  const config = deployment();
  if (!config) redirect("/dashboard");
  if (!sameOrigin(new Request(config.publicOrigin, { headers: await headers() }), false, true)) notFound();
  if (validSession((await cookies()).get(SESSION_COOKIE)?.value)) redirect("/dashboard");
  return <main className="operator-login"><div className="login-frame"><Link href="/" className="landing-brand"><TargetIcon />reliability.</Link><span className="landing-eyebrow">OPERATOR ACCESS</span><h1>Back to the evidence.</h1><p>Use your operator access key to open this workspace.</p><OperatorLogin /><div className="login-footnote">Single-operator access · Session expires after 8 hours.<br />Provider credentials never belong in this form.</div><Link className="landing-link" href="/">← Back to the product</Link></div></main>;
}
