import { CheckIcon, Cross2Icon, QuestionMarkCircledIcon, ExclamationTriangleIcon } from "@radix-ui/react-icons";
import { humanize } from "@/lib/presentation";

export function Status({ value }: { value: string }) {
  const tone = ["HEALTHY", "VERIFIED", "RESOLVED", "COMPLETED"].includes(value) ? "positive"
    : ["UNHEALTHY", "NOT_RECOVERED", "REJECTED"].includes(value) ? "negative"
    : ["DEGRADED", "OPEN", "INVESTIGATING", "PENDING", "EXECUTING", "ACCEPTED", "INCOMPLETE"].includes(value) ? "warning" : "neutral";
  return <span className={`status status-${tone}`}><span className="status-dot" />{humanize(value.toLowerCase())}</span>;
}
export function Source({ synthetic }: { synthetic: boolean }) {
  return <span className={`source ${synthetic ? "source-synthetic" : ""}`}>{synthetic ? "Synthetic" : "Non-synthetic"}</span>;
}
export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return <div className="empty-state"><QuestionMarkCircledIcon className="mb-3 size-7 text-slate-400" /><h3 className="font-medium text-slate-700">{title}</h3>{children && <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">{children}</p>}</div>;
}
export function Notice({ children }: { children: React.ReactNode }) {
  return <div className="notice" role="status"><ExclamationTriangleIcon className="mt-0.5 size-4 shrink-0" /><div>{children}</div></div>;
}
export function Evidence({ value, label = "View sanitized evidence" }: { value: unknown; label?: string }) {
  return <details className="evidence"><summary>{label}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}
export function VerificationScope() {
  return <div className="mt-4 space-y-2 text-xs text-slate-500"><p className="flex gap-2"><CheckIcon className="size-4 shrink-0" />Recovery proof is limited to required n8n nodes.</p><p className="flex gap-2"><Cross2Icon className="size-4 shrink-0" />Customer delivery and root cause remain unverified.</p></div>;
}
