"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ActivityLogIcon, ArrowRightIcon, ArrowTopRightIcon, CheckIcon, ChevronRightIcon,
  DashboardIcon, GlobeIcon, LayersIcon, LightningBoltIcon, MagnifyingGlassIcon,
  MixerHorizontalIcon, ReloadIcon, ResetIcon, RowsIcon, TargetIcon, TimerIcon,
} from "@radix-ui/react-icons";
import type { Check, Incident, Snapshot } from "@/lib/contracts";
import { actionLabel, age, humanize, isStale, latestChecks, matches, summary } from "@/lib/presentation";
import { Empty, Evidence, Notice, Source, Status, VerificationScope } from "./primitives";
import { Investigation } from "./investigation";
import { IncidentDrawer } from "./incident-drawer";

type View = "Overview" | "Incidents" | "Checks" | "Activity" | "Connections";
type Provenance = "all" | "non-synthetic" | "synthetic";
const navigation = [{ name: "Overview", icon: DashboardIcon }, { name: "Incidents", icon: TargetIcon },
  { name: "Checks", icon: RowsIcon }, { name: "Activity", icon: ActivityLogIcon }, { name: "Connections", icon: MixerHorizontalIcon }] as const;
const descriptions: Record<View, string> = {
  Overview: "The signals, the evidence, and your next move.", Incidents: "Follow each failure from observation to verified recovery.",
  Checks: "Recorded observations, with their source and timestamp intact.", Activity: "A traceable record of approvals, actions, and recovery proof.",
  Connections: "Know what is enabled before drawing a conclusion.",
};

export function Dashboard() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [view, setView] = useState<View>("Overview");
  const [source, setSource] = useState<Provenance>("all");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState(false);
  const [now, setNow] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const refresh = useCallback(async () => {
    controller.current?.abort();
    const active = new AbortController(); controller.current = active;
    setPending(true); setError(false);
    try {
      const response = await fetch("/api/dashboard", { cache: "no-store", signal: active.signal });
      if (!response.ok) throw new Error("unavailable");
      const result = await response.json() as Snapshot;
      if (!active.signal.aborted) { setData(result); setNow(Date.now()); }
    } catch { if (!active.signal.aborted) setError(true); }
    finally { if (!active.signal.aborted) setPending(false); }
  }, []);
  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    function focusSearch(event: KeyboardEvent) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey || document.querySelector("dialog[open]")) return;
      if (event.target instanceof HTMLElement && event.target.closest("input,textarea,select,[contenteditable]")) return;
      event.preventDefault(); document.getElementById("record-search")?.focus();
    }
    document.addEventListener("keydown", focusSearch);
    return () => { window.clearTimeout(initial); controller.current?.abort(); window.clearInterval(timer); document.removeEventListener("keydown", focusSearch); };
  }, [refresh]);
  const includeSource = (synthetic: boolean) => source === "all" || synthetic === (source === "synthetic");
  const checks = (data?.checks.data ?? []).filter((c) => includeSource(c.synthetic) && matches(search, c.component, c.category, c.kind, c.id, c.status));
  const incidents = (data?.incidents.data ?? []).filter((i) => includeSource(i.synthetic) && matches(search, i.title, i.component, i.id));
  const active = incidents.filter((i) => i.status !== "RESOLVED");
  const latest = latestChecks(checks);
  const healthy = latest.filter((c) => c.status === "HEALTHY" && !isStale(c, now));
  const uncertain = latest.filter((c) => ["UNKNOWN", "CHECK_FAILED"].includes(c.status) || isStale(c, now));
  const actions = (data?.actions.data ?? []).filter((a) => includeSource(a.synthetic) && matches(search, a.execution_id, a.id, a.workflow_id));
  const waiting = actions.filter((a) => a.state === "PENDING" && Date.parse(a.expires_at) > now);
  const historyUnavailable = !!data && (!data.services.data || !data.checks.data || !data.incidents.data);
  const hasSynthetic = source !== "non-synthetic" && ((data?.checks.data ?? []).some((c) => c.synthetic) || data?.agent.data?.mode === "fixture");
  const changeView = (next: View) => { setView(next); setFilter("all"); };

  return <div className="workspace">
    <a href="#main" className="skip-link">Skip to workspace</a>
    <aside className="sidebar">
      <Link className="brand" href="/" aria-label="Reliability home"><span className="brand-symbol"><TargetIcon /></span><span>Reliability<span className="brand-subtitle">AI RELIABILITY AGENT</span></span></Link>
      <div className="workspace-switch"><span className="workspace-avatar">L</span><span className="min-w-0"><strong>Local workspace</strong><small>Operator environment</small></span><ChevronRightIcon className="ml-auto size-4 text-slate-500" /></div>
      <p className="nav-label">WORKSPACE</p>
      <nav aria-label="Main navigation" className="space-y-1">{navigation.map(({ name, icon: Icon }) => <button key={name} className={`nav-item ${view === name ? "nav-active" : ""}`} onClick={() => changeView(name)} aria-current={view === name ? "page" : undefined}><Icon className="size-[18px]" />{name}{name === "Incidents" && active.length > 0 && <span className="nav-count">{active.length}</span>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="guard-icon"><CheckIcon /></div><p className="text-[13px] font-medium text-slate-200">Human in the loop.</p><p className="mt-2 text-xs leading-5 text-slate-400">Every remediation needs explicit operator approval.</p><div className="sidebar-divider" /><span className="flex items-center gap-2 text-xs text-slate-400"><span className="size-1.5 rounded-full bg-emerald-400" />Local access only<span className="ml-auto font-mono text-[10px]">PHASE 13</span></span></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="flex min-w-0 items-center gap-2 text-xs text-slate-400"><LayersIcon className="size-4" /><span className="hidden sm:inline">Workspace</span><ChevronRightIcon /><span className="font-medium text-slate-700">{view}</span></div><div className="flex items-center gap-3"><span className="local-tag">LOCAL</span><span className="topbar-divider" /><div className="operator-mark" aria-label="Local operator">OP</div></div></header>
      <main id="main" className="main-content">
        <div className="page-heading"><div><p className="eyebrow">OPERATIONS, WITH CONTEXT</p><h1>{view === "Overview" ? "Reliability overview" : view}</h1><p className="mt-2 text-sm text-slate-500">{descriptions[view]}</p></div><button className="button-secondary shrink-0" onClick={() => void refresh()} disabled={pending}><ReloadIcon className={`size-4 ${pending ? "refreshing" : ""}`} />{pending ? "Refreshing…" : "Refresh records"}</button></div>
        {error && <div className="mb-5"><Notice>Workspace refresh failed.{data ? " Previous records are retained and may be stale." : " Start the local frontend and backend, then refresh."}</Notice></div>}
        {data && !data.health.data && <div className="mb-5"><Notice>Backend connection unavailable. Monitored-system health cannot be inferred from a connection failure.</Notice></div>}
        {historyUnavailable && <div className="mb-5"><Notice>Some history is unavailable. Storage may be disabled, need an explicit migration, or be unreachable. Missing records are not evidence of healthy systems.</Notice></div>}
        <div className="toolbar"><div className="source-toggle" role="group" aria-label="Evidence source">{([['all', 'All sources'], ['non-synthetic', 'Non-synthetic'], ['synthetic', 'Synthetic']] as const).map(([value, label]) => <button key={value} aria-pressed={source === value} className={source === value ? "selected" : ""} onClick={() => setSource(value)}>{label}</button>)}</div><label className="search"><MagnifyingGlassIcon className="size-4 shrink-0" /><input id="record-search" aria-label="Search records" placeholder="Search records…" value={search} onChange={(e) => setSearch(e.target.value)} /><kbd>/</kbd></label></div>
        {hasSynthetic && <div className="fixture-banner"><span className="fixture-dot" /><strong>Synthetic evidence is included.</strong><span>Fixture results do not establish live integrations or customer outcomes.</span></div>}
        {pending && !data ? <Loading /> : data && <>
          {view === "Overview" && <>
            <section className="metrics" aria-label="Current view summary"><Metric label="Recent healthy signals" value={data.checks.data ? healthy.length : "—"} note="Under 5 minutes old" icon={<ActivityLogIcon />} /><Metric label="Open incidents" value={data.incidents.data ? active.length : "—"} note="In the loaded records" icon={<TargetIcon />} tone={active.length ? "attention" : ""} /><Metric label="Needs more evidence" value={data.checks.data ? uncertain.length : "—"} note="Unknown, failed checks, or stale" icon={<MagnifyingGlassIcon />} /><Metric label="Awaiting approval" value={data.actions.data ? waiting.length : "—"} note="Unexpired operator requests" icon={<TimerIcon />} /></section>
            <div className="overview-grid"><div className="min-w-0 space-y-6">
              <section className="signal-banner"><div><span className="signal-kicker"><span className={`size-1.5 rounded-full ${active.length ? "bg-amber-500" : "bg-emerald-600"}`} />YOUR ATTENTION, DIRECTED</span><h2>{historyUnavailable ? "The evidence is incomplete." : active.length ? `${active.length === 1 ? "One incident needs" : `${active.length} incidents need`} a closer look.` : latest.length ? "Start with what the evidence says." : "Ready for your first signal."}</h2><p>{active.length ? "Inspect the failure, examine the evidence, and choose a supported next step." : "Run a bounded investigation to collect observations. A healthy backend alone doesn’t establish system health."}</p><button className="text-button" onClick={() => active[0] ? setSelected(active[0].id) : changeView("Connections")}>{active.length ? "Inspect latest incident" : "Review connection policy"}<ArrowRightIcon /></button></div><SignalArtwork /></section>
              <section className="panel"><SectionHeading title="Service signals" subtitle="Latest observation per service and check type" action="All checks" onClick={() => changeView("Checks")} /><ServiceSignals checks={latest} history={checks} now={now} unavailable={!data.checks.data} /></section>
              <section className="panel"><SectionHeading title="Active incidents" subtitle="Failures linked to persisted evidence" action="View all" onClick={() => changeView("Incidents")} /><IncidentList incidents={active.slice(0, 4)} onSelect={setSelected} now={now} unavailable={!data.incidents.data} /></section>
            </div><aside className="min-w-0 space-y-6"><Investigation agent={data.agent} onComplete={refresh} /><section className="panel p-6"><div className="mb-4 flex items-center gap-2 text-sm font-medium"><ResetIcon className="size-4 text-emerald-700" />Recovery, with proof</div><p className="text-sm leading-6 text-slate-500">A retry receipt starts verification. Only validated execution evidence can close the incident.</p><div className="recovery-steps"><span>Observe</span><ChevronRightIcon /><span>Approve</span><ChevronRightIcon /><span>Verify</span></div><VerificationScope /><button className="text-button mt-5" onClick={() => changeView("Activity")}>Open action audit<ArrowRightIcon /></button></section></aside></div>
          </>}
          {view === "Incidents" && <section className="panel"><div className="section-heading"><div><h2>Incident register</h2><p>Up to 100 latest incidents. Counts refer to this view.</p></div><select aria-label="Incident status" className="filter-select" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">All states</option><option value="OPEN">Open</option><option value="INVESTIGATING">Investigating</option><option value="RESOLVED">Resolved</option></select></div><IncidentList incidents={incidents.filter((i) => filter === "all" || i.status === filter)} now={now} onSelect={setSelected} unavailable={!data.incidents.data} /></section>}
          {view === "Checks" && <section className="panel"><div className="section-heading"><div><h2>Observation history</h2><p>Latest 100 records. Refresh reads history; it does not run new checks.</p></div><select className="filter-select" aria-label="Check status" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">All statuses</option>{['HEALTHY', 'UNHEALTHY', 'DEGRADED', 'UNKNOWN', 'CHECK_FAILED'].map((s) => <option key={s}>{s}</option>)}</select></div><CheckHistory checks={checks.filter((c) => filter === "all" || c.status === filter)} now={now} unavailable={!data.checks.data} /></section>}
          {view === "Activity" && <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr]"><section className="panel"><SectionHeading title="Approval & action audit" subtitle="Latest 100 actions; no writes are available in the browser" />{!data.actions.data ? <Empty title="Action history unavailable">Check backend storage and access settings.</Empty> : !actions.length ? <Empty title="No matching action records">The local operator CLI creates and approves one-shot actions against incident evidence.</Empty> : <div className="divide-y divide-slate-100">{actions.map((a) => <div key={a.id} className="p-6"><div className="mb-3 flex flex-wrap items-center gap-2"><Status value={a.state} /><Source synthetic={a.synthetic} /><span className="ml-auto text-xs text-slate-400">{age(a.created_at, now)}</span></div><h3 className="font-medium">{actionLabel(a, now)}</h3><p className="mt-1 break-all text-xs text-slate-500">Execution {a.execution_id}{a.new_execution_id ? ` → ${a.new_execution_id}` : ""} · {a.workflow_id}</p><p className="mt-3 text-sm leading-6 text-slate-500">{a.state === "UNKNOWN" ? "Dispatch outcome is uncertain. Do not automatically resend this action." : a.state === "ACCEPTED" ? "Provider receipt recorded. Recovery requires separate evidence." : a.risk}</p><button className="text-button mt-3" onClick={() => setSelected(a.incident_id)}>View incident<ArrowTopRightIcon /></button></div>)}</div>}</section><section className="panel self-start"><SectionHeading title="Verification records" subtitle="Historical proof, not a fresh provider observation" />{!data.verifications.data ? <Empty title="Verification history unavailable" /> : !(data.verifications.data.filter((v) => {
            const service = data.services.data?.find((s) => s.id === v.service_id);
            return service ? includeSource(service.synthetic) && matches(search, v.id, v.workflow_id, v.new_execution_id) : source === "all" && matches(search, v.id, v.workflow_id, v.new_execution_id);
          })).length ? <Empty title="No matching verification records">Only successful node evidence can establish scoped recovery.</Empty> : data.verifications.data.filter((v) => {
            const service = data.services.data?.find((s) => s.id === v.service_id);
            return service ? includeSource(service.synthetic) && matches(search, v.id, v.workflow_id, v.new_execution_id) : source === "all" && matches(search, v.id, v.workflow_id, v.new_execution_id);
          }).map((v) => <div key={v.id} className="border-t border-slate-100 p-6"><div className="flex flex-wrap gap-2"><Status value={v.result} />{data.services.data?.find((s) => s.id === v.service_id) && <Source synthetic={data.services.data.find((s) => s.id === v.service_id)!.synthetic} />}</div><p className="mt-3 text-sm">Execution {v.new_execution_id} · {humanize(v.reason)}</p><p className="mt-2 text-xs text-slate-400">Recorded {age(v.observed_at, now)} · n8n required nodes</p><VerificationScope /><button className="text-button mt-4" onClick={() => setSelected(v.incident_id)}>Inspect proof<ArrowTopRightIcon /></button></div>)}</section></div>}
          {view === "Connections" && <Connections data={data} />}
          <footer className="workspace-footer"><span className="flex items-center gap-2"><span className={`size-1.5 rounded-full ${data.health.data ? "bg-emerald-600" : "bg-slate-400"}`} />Backend process {data.health.data ? "reachable" : "unavailable"}<span className="hidden sm:inline">· liveness only</span></span><span>Records fetched {age(data.fetchedAt, now)} · Manual refresh</span></footer>
        </>}
      </main>
    </div>
    {selected && <IncidentDrawer identifier={selected} onClose={() => setSelected(null)} actions={data?.actions.data ?? null} now={now} />}
  </div>;
}

function Metric({ label, value, note, icon, tone = "" }: { label: string; value: number | string; note: string; icon: React.ReactNode; tone?: string }) {
  return <div className={`metric ${tone}`}><div className="flex items-center justify-between gap-3"><span>{label}</span><span className="metric-icon">{icon}</span></div><strong>{value}</strong><small>{note}</small></div>;
}
function SectionHeading({ title, subtitle, action, onClick }: { title: string; subtitle: string; action?: string; onClick?: () => void }) {
  return <div className="section-heading"><div><h2>{title}</h2><p>{subtitle}</p></div>{action && <button className="text-button shrink-0" onClick={onClick}>{action}<ArrowRightIcon /></button>}</div>;
}
function ServiceSignals({ checks, history, now, unavailable }: { checks: Check[]; history: Check[]; now: number; unavailable: boolean }) {
  if (!checks.length) return <Empty title={unavailable ? "Check history unavailable" : "No matching observations"}>A bounded investigation or a registered backend check will add evidence here.</Empty>;
  return <div>{checks.slice(0, 8).map((c) => {
    const recent = history.filter((h) => h.service_id === c.service_id && h.kind === c.kind).sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at)).slice(-24);
    const Icon = c.category === "n8n" ? LightningBoltIcon : c.category === "website" ? GlobeIcon : LayersIcon;
    return <div className="service-row" key={`${c.service_id}:${c.kind}`}><div className={`service-icon ${c.status === "UNHEALTHY" ? "service-attention" : ""}`}><Icon /></div><div className="min-w-0 flex-1"><h3 className="truncate text-[13px] font-medium" title={c.component}>{c.component.replace("workflow:", "Workflow · ")}</h3><p className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">{humanize(c.kind)}<span>·</span><span>{age(c.observed_at, now)}</span>{isStale(c, now) && <span className="text-amber-700">· Stale</span>}<Source synthetic={c.synthetic} /></p></div><div className="check-strip" aria-label={`${recent.length} recorded ${c.kind} observations`}>{recent.map((h) => <span key={h.id} className={`strip-${h.status.toLowerCase()}`} title={`${h.status} · ${h.observed_at}`} />)}</div><Status value={c.status} /></div>;
  })}<div className="px-6 py-3 text-[11px] text-slate-400">{checks.length > 8 ? `Showing 8 of ${checks.length} signals. ` : ""}Each bar is a recorded check. Status is historical; stale evidence needs a new check.</div></div>;
}
function IncidentList({ incidents, onSelect, now, unavailable }: { incidents: Incident[]; onSelect: (id: string) => void; now: number; unavailable: boolean }) {
  if (!incidents.length) return <Empty title={unavailable ? "Incident history unavailable" : "No matching incidents"}>{unavailable ? "Restore history access to inspect persisted incidents." : "Only persisted unhealthy observations can create incidents. Missing incidents do not prove healthy systems."}</Empty>;
  return <div>{incidents.map((i) => <button key={i.id} className="incident-row" onClick={() => onSelect(i.id)}><span className={`incident-severity ${i.severity === "high" && i.status !== "RESOLVED" ? "severity-high" : ""}`}><TargetIcon /></span><span className="min-w-0 flex-1 text-left"><span className="flex flex-wrap items-center gap-2"><strong className="text-[13px] font-medium">{i.component.replace("workflow:", "Workflow · ")}</strong><Source synthetic={i.synthetic} /></span><span className="mt-1.5 block text-xs text-slate-500">{humanize(i.kind)} · {i.observation_count} observations · {age(i.created_at, now)}</span><span className="mt-1 block text-[11px] text-slate-400">Root cause unknown{ i.status === "RESOLVED" ? " · Required-node recovery only" : ""}</span></span><span className="flex shrink-0 items-center gap-3"><Status value={i.status} /><ChevronRightIcon className="size-4 text-slate-400" /></span></button>)}</div>;
}
function CheckHistory({ checks, now, unavailable }: { checks: Check[]; now: number; unavailable: boolean }) {
  return !checks.length ? <Empty title={unavailable ? "Check history unavailable" : "No matching checks"}>Try a different filter, or run a registered backend check.</Empty> : <div className="divide-y divide-slate-100">{checks.map((c) => <div className="px-6 py-5" key={c.id}><div className="flex flex-wrap items-center justify-between gap-3"><div className="min-w-0"><h3 className="break-all text-sm font-medium">{c.component} <span className="font-normal text-slate-400">/ {c.kind}</span></h3><p className="mt-2 text-xs text-slate-500">{summary(c)}</p></div><Status value={c.status} /></div><div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400"><Source synthetic={c.synthetic} /><time dateTime={c.observed_at} title={c.observed_at}>{age(c.observed_at, now)}</time>{isStale(c, now) && <span className="text-amber-700">Stale observation</span>}<span className="font-mono text-[10px]">{c.id.slice(0, 8)}</span></div><Evidence value={c.payload} /></div>)}</div>;
}
function Connections({ data }: { data: Snapshot }) {
  return <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]"><section className="panel"><SectionHeading title="Workspace capabilities" subtitle="Configuration is separate from successful connectivity" />{[
    { title: "Backend process", value: data.health.data ? "Reachable" : "Unavailable", detail: "Process liveness only. This does not verify monitored systems." },
    { title: "Application history", value: data.storage.data?.state ?? "Unavailable", detail: `Storage: ${data.storage.data?.mode ?? "unknown"}. Migrations run explicitly, never on startup.` },
    { title: "Investigation", value: data.agent.data?.mode ?? "Unavailable", detail: data.agent.data?.mode === "fixture" ? "Scripted inference with synthetic provider fixtures. Live AI remains unverified." : "Live mode can send your question and restricted evidence to Nebius. Keep secrets out of questions." },
    { title: "n8n retry policy", value: data.actionPolicy.data?.mode ?? "Unavailable", detail: "One-shot local operator approval. A browser cannot approve or execute a retry." },
    { title: "Recovery verification", value: data.recoveryPolicy.data?.mode ?? "Unavailable", detail: "Local operator CLI only. Exact new execution and configured required nodes must pass." },
  ].map((c) => <div className="border-t border-slate-100 px-6 py-5" key={c.title}><div className="flex items-center justify-between gap-4"><h3 className="text-sm font-medium">{c.title}</h3><span className="source">{humanize(c.value)}</span></div><p className="mt-2 max-w-xl text-xs leading-6 text-slate-500">{c.detail}</p></div>)}</section><section className="panel self-start p-6"><div className="mb-4 grid size-10 place-content-center rounded-xl bg-emerald-50 text-emerald-700"><LayersIcon className="size-5" /></div><h2 className="text-base font-medium">Built around evidence.</h2><p className="mt-3 text-sm leading-6 text-slate-500">This local workspace reads the existing backend. Provider secrets stay there. A connection setting is never displayed as proof of a working integration.</p><div className="mt-5 border-t border-slate-100 pt-5 text-xs leading-6 text-slate-500">Production hosting and authenticated access controls belong to Phase 14. Keep both servers bound to loopback.</div></section></div>;
}
function Loading() { return <div role="status" aria-label="Loading workspace" className="space-y-6"><div className="skeleton h-32 rounded-2xl" /><div className="grid gap-6 lg:grid-cols-[1.8fr_1fr]"><div className="skeleton h-96 rounded-2xl" /><div className="skeleton h-80 rounded-2xl" /></div></div>; }
function SignalArtwork() {
  return <div className="signal-art" aria-hidden="true"><svg viewBox="0 0 180 180" fill="none"><circle cx="90" cy="90" r="72" stroke="currentColor" strokeOpacity=".12" /><circle cx="90" cy="90" r="48" stroke="currentColor" strokeOpacity=".19" /><circle cx="90" cy="90" r="24" stroke="currentColor" strokeOpacity=".25" /><path d="M18 90h144M90 18v144" stroke="currentColor" strokeOpacity=".1" /><circle cx="90" cy="90" r="7" fill="currentColor" /><circle cx="128" cy="60" r="4" fill="currentColor" /><circle cx="40" cy="141" r="4" fill="currentColor" fillOpacity=".35" /><path d="M90 90l38-30" stroke="currentColor" strokeDasharray="3 4" /></svg><span className="art-label">SIGNAL → CONTEXT</span></div>;
}
