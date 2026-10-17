"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, CheckIcon, CopyIcon, Cross2Icon, LockClosedIcon, TargetIcon } from "@radix-ui/react-icons";
import type { Action, IncidentDetail, ReadResult } from "@/lib/contracts";
import { actionLabel, age, humanize, summary } from "@/lib/presentation";
import { Empty, Evidence, Notice, Source, Status, VerificationScope } from "./primitives";

export function IncidentDrawer({ identifier, onClose, actions, now }: { identifier: string; onClose: () => void; actions: Action[] | null; now: number }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState(false);
  const [tab, setTab] = useState<"Overview" | "Evidence">("Overview");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement as HTMLElement | null;
    const abort = new AbortController();
    element?.showModal();
    async function load() {
      try {
        const response = await fetch(`/api/incidents/${identifier}`, { cache: "no-store", signal: abort.signal });
        if (!response.ok) throw new Error("unavailable");
        const result = await response.json() as ReadResult<IncidentDetail>;
        if (!result.data) throw new Error("unavailable");
        if (!abort.signal.aborted) setDetail(result.data);
      } catch { if (!abort.signal.aborted) setError(true); }
    }
    void load();
    return () => { abort.abort(); element?.close(); previous?.focus(); };
  }, [identifier]);
  const incidentActions = (actions ?? []).filter((a) => a.incident_id === identifier);
  const incident = detail?.incident;
  const assessment = detail?.assessments.data?.[0];
  const proof = detail?.proof?.data;
  return <dialog ref={dialog} className="incident-dialog" onCancel={(e) => { e.preventDefault(); onClose(); }} aria-labelledby="incident-title"><header className="drawer-header"><div className="flex items-center gap-2 text-xs text-slate-500"><TargetIcon />INCIDENT DETAIL</div><button className="icon-button" onClick={onClose} aria-label="Close incident"><Cross2Icon /></button></header><div className="drawer-content">
    <div className="mb-5 flex flex-wrap items-center gap-2">{incident && <><Status value={incident.status} /><Source synthetic={incident.synthetic} /><span className="source">{humanize(incident.severity)} severity</span></>}</div><h2 id="incident-title" className="break-words text-2xl font-medium tracking-tight">{incident?.component.replace("workflow:", "Workflow · ") ?? "Incident evidence"}</h2><p className="mt-3 break-all font-mono text-[11px] text-slate-400">{identifier}</p>
    {error ? <div className="mt-6"><Notice>Incident details are unavailable. Close this panel and refresh records to retry.</Notice></div> : !detail ? <div className="skeleton mt-8 h-64 rounded-xl" role="status" aria-label="Loading incident" /> : <>
      <div className="drawer-tabs" role="group" aria-label="Incident detail view">{(["Overview", "Evidence"] as const).map((value) => <button key={value} aria-pressed={tab === value} className={tab === value ? "selected" : ""} onClick={() => setTab(value)}>{value}{value === "Evidence" && <span>{detail.observations.data?.length ?? "—"}</span>}</button>)}</div>
      {tab === "Overview" ? <div className="space-y-7"><div className="grid grid-cols-2 gap-5 rounded-xl border border-slate-200 bg-slate-50/60 p-5"><Info label="First recorded" value={age(detail.incident.created_at, now)} /><Info label="Linked observations" value={String(detail.incident.observation_count)} /><Info label="Supported hypothesis" value={humanize(assessment?.hypothesis ?? "unknown")} /><Info label="Root cause" value="Unknown · unverified" /></div>
        {!detail.assessments.data && <Notice>Incident assessments are unavailable; no diagnosis can be inferred.</Notice>}
        <section><h3 className="drawer-label">DIAGNOSIS</h3><p className="mt-3 text-sm leading-7 text-slate-600">{assessment ? `The stored assessment supports ${humanize(assessment.hypothesis).toLowerCase()}. This is a hypothesis based on linked evidence, not a verified root cause.` : "No validated assessment is stored for this incident. Inspect the evidence or run an investigation before drawing a conclusion."}</p>{assessment && <p className="mt-2 text-xs text-slate-400">Source: {humanize(assessment.inference_source)} · Check {assessment.check_id.slice(0, 8)}</p>}</section>
        <section><h3 className="drawer-label">RECOMMENDED NEXT STEP</h3>{assessment ? <ol className="mt-3 space-y-3">{assessment.recommended_steps.map((step) => <li className="flex gap-3 text-sm text-slate-600" key={step}><ArrowRightIcon className="mt-0.5 size-4 shrink-0 text-emerald-700" />{humanize(step)}</li>)}</ol> : <p className="mt-3 text-sm text-slate-500">Collect and inspect evidence before choosing remediation.</p>}</section>
        <section className="operator-section"><div className="flex items-center gap-2"><LockClosedIcon className="size-4 text-emerald-700" /><h3 className="text-sm font-medium">Operator approval & action</h3></div><p className="mt-3 text-xs leading-6 text-slate-500">Approval and execution use the local operator CLI. A retry can repeat external side effects. This dashboard cannot approve, execute, verify, or resolve.</p>{!actions ? <Notice>Action history is unavailable.</Notice> : !incidentActions.length ? <p className="mt-4 text-xs text-slate-500">No action in the latest 100 action records is linked to this incident.</p> : incidentActions.map((a) => <div key={a.id} className="mt-4 border-t border-slate-200 pt-4"><div className="flex flex-wrap items-center justify-between gap-3"><strong className="text-sm font-medium">{actionLabel(a, now)}</strong><Status value={a.state} /></div><p className="mt-2 text-xs text-slate-500">Execution {a.execution_id}{a.new_execution_id ? ` → ${a.new_execution_id}` : ""}</p><p className="mt-2 text-xs leading-6 text-slate-500">{a.state === "UNKNOWN" ? "Dispatch is uncertain. Do not resend or reset this consumed action." : a.state === "ACCEPTED" ? "Provider receipt accepted. Recovery must be independently verified." : a.risk}</p></div>)}<details className="mt-4"><summary className="cursor-pointer text-xs font-medium text-emerald-800">Local operator reference</summary><p className="mt-3 text-xs leading-6 text-slate-500">From backend/ with the project environment active, inspect CLI help before planning an action.</p><code className="command-block">python -m app.actions.cli --help</code><button className="text-button mt-2" onClick={async () => {
          try { await navigator.clipboard.writeText("python -m app.actions.cli --help"); setCopied(true); } catch { setCopied(false); }
        }}>{copied ? <CheckIcon /> : <CopyIcon />}{copied ? "Copied" : "Copy CLI reference"}</button></details></section>
        <section><h3 className="drawer-label">RECOVERY VERIFICATION</h3><div className="mt-3 flex flex-wrap gap-2"><Status value={proof?.result ?? (detail.incident.status === "RESOLVED" ? "UNKNOWN" : "INCONCLUSIVE")} />{detail.incident.status === "RESOLVED" && <span className="source">Required-node resolution</span>}</div><p className="mt-3 text-sm leading-6 text-slate-500">{proof ? `Historical proof for execution ${proof.new_execution_id}: ${humanize(proof.reason).toLowerCase()}. This panel does not perform a fresh provider read.` : detail.incident.status === "RESOLVED" ? "The incident references recovery proof, but the proof could not be loaded. Restore access before interpreting the resolution." : "No successful recovery proof is linked to this incident."}</p>{proof && <Evidence label="Inspect stored recovery proof" value={proof} />}<VerificationScope /></section>
      </div> : <section>{!detail.observations.data ? <Notice>Linked observations could not be loaded.</Notice> : !detail.observations.data.length ? <Empty title="No linked evidence returned" /> : <div className="space-y-5">{detail.observations.data.map((c) => <div className="rounded-xl border border-slate-200 p-5" key={c.id}><div className="flex flex-wrap items-center gap-2"><Status value={c.status} /><Source synthetic={c.synthetic} /></div><p className="mt-4 text-sm leading-6">{summary(c)}</p><p className="mt-2 break-all font-mono text-[10px] text-slate-400">{c.id} · {c.observed_at}</p><Evidence value={c.payload} /></div>)}</div>}<p className="mt-5 text-xs text-slate-400">Up to 100 linked observations. Source text is displayed as data.</p></section>}
    </>}
  </div></dialog>;
}
function Info({ label, value }: { label: string; value: string }) { return <div><dt className="text-[11px] text-slate-500">{label}</dt><dd className="mt-1.5 break-words text-xs font-medium text-slate-800">{value}</dd></div>; }
