"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRightIcon, GlobeIcon, LayersIcon, LightningBoltIcon } from "@radix-ui/react-icons";
import type { ReadResult } from "@/lib/contracts";
import { monitoringSchema, type Monitoring, type N8nResults, type OperatorRequest, type WebsiteResults } from "@/lib/monitoring";
import { Evidence, Notice, Source, Status } from "./primitives";
import { humanize } from "@/lib/presentation";

const errorMessage = (code: string | null) => code === "invalid_input"
  ? "Use a public http:// or https:// address without a password, query string, or fragment."
  : code === "busy_or_limit" ? "Another check is running, or the 25-website limit has been reached. Reload the connections before trying again."
  : code === "access_unavailable" ? "This operation is unavailable. The backend may still be updating."
  : "The request could not finish. Check the connection and try again; no successful check is being claimed.";

export function MonitoringPanel({ onComplete, compact = false, onConnections }: {
  onComplete: () => Promise<void>; compact?: boolean; onConnections?: () => void;
}) {
  const [capabilities, setCapabilities] = useState<Monitoring | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [url, setUrl] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [results, setResults] = useState<WebsiteResults | null>(null);
  const [n8n, setN8n] = useState<N8nResults | null>(null);
  const [executionId, setExecutionId] = useState("");
  const [infrastructure, setInfrastructure] = useState<Record<string, unknown> | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch("/api/monitoring", { cache: "no-store", signal });
      const envelope = await response.json();
      const parsed = monitoringSchema.safeParse(envelope.data);
      if (!response.ok || !parsed.success) throw new Error("unavailable");
      setCapabilities(parsed.data); setLoadError(false);
    } catch { if (!signal?.aborted) setLoadError(true); }
  }, []);
  useEffect(() => { const controller = new AbortController(); const initial = window.setTimeout(() => void load(controller.signal), 0); return () => { window.clearTimeout(initial); controller.abort(); }; }, [load]);

  async function command<T>(request: OperatorRequest): Promise<T | null> {
    setPending(request.action); setMessage(null);
    try {
      const response = await fetch("/api/monitoring", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request), signal: AbortSignal.timeout(60_000) });
      const result: ReadResult<T> = await response.json();
      if (!response.ok || !result.data) { setMessage(errorMessage(result.error)); return null; }
      return result.data;
    } catch { setMessage(errorMessage(null)); return null; }
    finally { setPending(null); }
  }

  async function register(event: React.FormEvent) {
    event.preventDefault();
    const result = await command({ action: "register_website", url });
    if (result) { setUrl(""); setMessage("Website saved. Click Run checks to collect its first observations."); await load(); }
  }
  async function checkWebsite(identifier: string) {
    setResults(null);
    const result = await command<WebsiteResults>({ action: "check_website", target_id: identifier });
    if (result) { setResults(result); await onComplete(); }
  }
  async function inspect(request: OperatorRequest) {
    setN8n(null);
    const result = await command<N8nResults>(request);
    if (result) { setN8n(result); if (request.action === "n8n_execution") await onComplete(); }
  }

  return <div className="monitoring space-y-6">
    <section className="panel p-6" aria-label="Website setup and checks">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="eyebrow">START WITH A REAL SYSTEM</p><h2 className="mt-2 text-lg font-medium">Connect your website</h2><p className="mt-2 max-w-xl text-sm leading-6 text-slate-500">Save a website address, then check its response, DNS, and security certificate. No AI key is needed.</p></div><GlobeIcon className="size-5 text-emerald-600" /></div>
      <form onSubmit={(event) => void register(event)} className="mt-5 flex flex-wrap items-end gap-3"><label className="min-w-0 flex-1 text-xs text-slate-400" htmlFor="website-url">Website URL<input id="website-url" type="url" required maxLength={2048} value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" className="mt-2 w-full" disabled={!!pending || !capabilities || !!capabilities.websites.error} /></label><button className="button-primary" disabled={!!pending || !capabilities || !!capabilities.websites.error}>{pending === "register_website" ? "Saving…" : "Save website"}</button></form>
      <p className="mt-3 text-xs leading-5 text-slate-400">Manual checks only. These checks do not submit forms, create bookings, or prove every business flow works. Refresh records reloads saved evidence.</p>
      {loadError && <div className="mt-4"><Notice>Connection settings are unavailable. The backend may be waking up. <button className="text-button" onClick={() => void load()}>Reload connections</button></Notice></div>}
      {capabilities?.websites.error && <div className="mt-4"><Notice>Website setup needs working application storage and its latest migration. Existing evidence is retained.</Notice></div>}
      {message && <div className="mt-4"><Notice>{message}</Notice></div>}
      <div className="mt-4 divide-y divide-slate-800">{capabilities?.websites.targets.map((target) => <div className="flex flex-wrap items-center justify-between gap-3 py-4" key={target.id}><div className="min-w-0"><p className="break-all text-sm font-medium">{target.url}</p><p className="mt-1 text-xs text-slate-400">Saved target · HTTP, DNS, TLS</p></div><button className="button-secondary" disabled={!!pending} onClick={() => void checkWebsite(target.id)}>{pending === "check_website" ? "Checking…" : "Run checks"}</button></div>)}</div>
      {capabilities && !capabilities.websites.error && !capabilities.websites.targets.length && <p className="mt-4 text-sm text-slate-400">No websites connected yet. Add the public address above.</p>}
      {results && <div className="mt-4 space-y-3" role="status">{results.results.map(({ check, history }) => <div className="rounded-lg border border-slate-800 p-4" key={check.check_type}><div className="flex items-center justify-between gap-3"><strong className="text-sm">{check.check_type === "ssl" ? "TLS certificate" : check.check_type.toUpperCase()}</strong><Status value={check.status} /></div><p className="mt-2 text-sm text-slate-400">{check.summary}</p><p className="mt-2 text-xs text-slate-400">{history.status === "saved" ? "Saved to Checks history." : "The observation was returned, but history was not saved. Run it again only when you want a fresh check."}</p><Evidence value={check.evidence} /></div>)}</div>}
      {compact && onConnections && <button className="text-button mt-5" onClick={onConnections}>Connect n8n and infrastructure<ArrowRightIcon /></button>}
    </section>

    {!compact && <>
      <section className="panel p-6" aria-label="n8n workflow inspection"><div className="flex justify-between gap-3"><div><p className="eyebrow">AUTOMATIONS</p><h2 className="mt-2 text-lg font-medium">Inspect n8n workflows</h2></div><LightningBoltIcon className="size-5 text-emerald-600" /></div>
        <p className="mt-3 text-sm leading-6 text-slate-500">Read saved workflow executions and inspect failed steps. This does not activate, edit, or retry a workflow.</p>
        <p className="mt-3 text-sm">{!capabilities ? "Checking configuration…" : capabilities.n8n.mode === "disabled" || !capabilities.n8n.configured ? "Needs connection: add your n8n API address and API key in the backend’s protected settings." : capabilities.n8n.synthetic ? "Synthetic demo connection. No real n8n instance is contacted." : "Live connection configured. A successful read is still required to verify access."}</p>
        <details className="mt-4 text-xs leading-6 text-slate-400"><summary>Connection setup</summary><p className="mt-2">An operator must set N8N_MODE=live, N8N_BASE_URL to your instance’s /api/v1 address, and N8N_API_KEY in Render’s protected environment settings. Use read access where available. Keep keys out of questions and website addresses.</p><p className="mt-2">n8n Cloud free trials do not include public API access. An API-enabled account or a separate self-hosted instance is required. <a className="underline" href="https://support.n8n.io/article/can-i-have-api-access-while-im-on-a-trial" target="_blank" rel="noreferrer">See n8n’s availability policy</a>.</p></details>
        <div className="mt-4 flex flex-wrap gap-3"><button className="button-secondary" disabled={!!pending || !capabilities?.n8n.configured || capabilities.n8n.mode === "disabled"} onClick={() => void inspect({ action: "n8n_workflows" })}>List workflows</button><button className="button-secondary" disabled={!!pending || !capabilities?.n8n.configured || capabilities.n8n.mode === "disabled"} onClick={() => void inspect({ action: "n8n_failed" })}>Find failed executions</button></div>
        <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); void inspect({ action: "n8n_execution", execution_id: executionId }); }}><label htmlFor="execution-id" className="min-w-0 flex-1 text-xs text-slate-400">Or inspect a known execution ID<input id="execution-id" className="mt-2 w-full" inputMode="numeric" pattern="[1-9][0-9]{0,18}" maxLength={19} required value={executionId} onChange={(event) => setExecutionId(event.target.value)} /></label><button className="button-secondary" disabled={!!pending || !capabilities?.n8n.configured || capabilities.n8n.mode === "disabled"}>Inspect execution</button></form>
        {pending?.startsWith("n8n_") && <p className="mt-4 text-sm" role="status">Reading n8n evidence…</p>}
        {n8n && <div className="mt-5 space-y-3"><Source synthetic={n8n.synthetic} />{n8n.status === "CHECK_FAILED" ? <Notice>Inspection could not be completed: {humanize(n8n.reason ?? "unknown")}. This is not proof that a workflow is broken.</Notice> : <><p className="text-xs text-slate-400">Read completed. Lists contain up to 25 records{n8n.next_cursor ? "; more records exist outside this page" : ""}. An inactive workflow is not itself a failed execution.</p>{n8n.workflows.map((workflow) => <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 py-3" key={workflow.id}><p className="break-all text-sm">Workflow {workflow.id} · {workflow.active ? "Active" : "Inactive"}</p><button className="text-button" disabled={!!pending} onClick={() => void inspect({ action: "n8n_failed", workflow_id: workflow.id })}>Inspect failures<ArrowRightIcon /></button></div>)}{n8n.executions.map((execution) => <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 py-3" key={execution.id}><p className="break-all text-sm">Execution {execution.id} · {execution.execution_state} · Workflow {execution.workflow_id}</p><button className="text-button" disabled={!!pending} onClick={() => void inspect({ action: "n8n_execution", execution_id: execution.id })}>Inspect evidence<ArrowRightIcon /></button></div>)}{n8n.operation !== "execution" && !n8n.workflows.length && !n8n.executions.length && <p className="text-sm">No records returned on this page. This does not establish overall system health.</p>}{n8n.execution && <><Status value={n8n.execution.status} /><p className="text-sm">{n8n.execution.summary}</p><Evidence value={n8n.execution} label="View execution evidence" /><p className="text-xs text-slate-400">Recorded execution evidence. Root cause and customer delivery remain unverified.</p></>}</>}</div>}
      </section>

      <section className="panel p-6" aria-label="Infrastructure inspection"><div className="flex justify-between gap-3"><div><p className="eyebrow">SUPPORTING SERVICES</p><h2 className="mt-2 text-lg font-medium">Check infrastructure</h2></div><LayersIcon className="size-5 text-emerald-600" /></div><p className="mt-3 text-sm leading-6 text-slate-500">These are separate monitoring connections. Using Supabase to save this app’s history does not automatically connect its monitoring API.</p>
        <div className="mt-4 divide-y divide-slate-800">{capabilities?.infrastructure.checks.map((check) => <div className="flex flex-wrap items-center justify-between gap-3 py-3" key={check.id}><span className="text-sm">{humanize(check.id)}</span><button className="button-secondary" disabled={!!pending || !check.configured} onClick={async () => { setInfrastructure(null); const result = await command<Record<string, unknown>>({ action: "infrastructure", check_id: check.id }); if (result) { setInfrastructure(result); await onComplete(); } }}>{check.configured ? "Run check" : "Needs connection"}</button></div>)}</div>
        <details className="mt-4 text-xs leading-6 text-slate-400"><summary>Connection setup</summary><p className="mt-2">Enable INFRASTRUCTURE_MODE=live in the backend. Vercel needs a token and deployment ID; Supabase monitoring needs a management token and project reference; PostgreSQL monitoring needs a separate restricted database login. No provider passwords are collected by this screen.</p></details>
        {infrastructure && <div className="mt-4"><Status value={String(infrastructure.status)} /><p className="mt-3 text-sm">{String(infrastructure.summary)}</p><Evidence value={infrastructure} /></div>}
      </section>
      {message && <Notice>{message}</Notice>}
    </>}
  </div>;
}
