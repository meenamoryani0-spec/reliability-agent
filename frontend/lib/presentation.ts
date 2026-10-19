import type { Action, Check } from "./contracts";

export function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/^\w/, (s) => s.toUpperCase());
}
export function latestChecks(checks: Check[]): Check[] {
  const result = new Map<string, Check>();
  for (const check of checks) {
    const key = `${check.service_id}:${check.kind}`;
    const current = result.get(key);
    if (!current || Date.parse(check.observed_at) > Date.parse(current.observed_at)) result.set(key, check);
  }
  return [...result.values()];
}
export function age(value: string, now: number): string {
  const seconds = Math.floor((now - Date.parse(value)) / 1000);
  if (seconds < -5) return "Clock ahead";
  if (seconds < 60) return "Just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
export function isStale(check: Check, now: number): boolean {
  const elapsed = now - Date.parse(check.observed_at);
  return elapsed > 300_000 || elapsed < -5000;
}
export function actionLabel(action: Action, now: number): string {
  if (action.state === "PENDING") return Date.parse(action.expires_at) <= now ? "Approval expired" : "Awaiting operator";
  return ({ ACCEPTED: "Retry accepted", EXECUTING: "Dispatch in progress", REJECTED: "Retry rejected", UNKNOWN: "Dispatch uncertain" })[action.state];
}
export function summary(check: Check): string {
  return typeof check.payload.summary === "string" ? check.payload.summary : `${humanize(check.kind)} observation`;
}
export function componentLabel(check: Check): string {
  const evidence = check.payload.evidence;
  if (check.category === "website" && evidence && typeof evidence === "object" && !Array.isArray(evidence)) {
    const hostname = (evidence as Record<string, unknown>).hostname;
    if (typeof hostname === "string" && /^[a-z0-9][a-z0-9.-]{0,251}[a-z0-9]$/.test(hostname)) return hostname;
  }
  return check.component.replace("workflow:", "Workflow · ");
}
export function matches(search: string, ...values: string[]): boolean {
  return values.join(" ").toLocaleLowerCase().includes(search.trim().toLocaleLowerCase());
}
