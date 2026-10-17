"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, LightningBoltIcon, LockClosedIcon, TargetIcon } from "@radix-ui/react-icons";
import type { ReadResult, Report, Snapshot } from "@/lib/contracts";
import { questionSchema } from "@/lib/contracts";
import { humanize } from "@/lib/presentation";
import { Evidence, Notice, Status } from "./primitives";

const FIXTURE_QUESTION = "Why are booking confirmations missing?";
export function Investigation({ agent, onComplete }: { agent: Snapshot["agent"]; onComplete: () => Promise<void> }) {
  const [question, setQuestion] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const submitting = useRef(false);
  useEffect(() => () => controller.current?.abort(), []);
  const enabled = agent.data && agent.data.mode !== "disabled" && agent.data.configured;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (submitting.current || !enabled) return;
    const parsed = questionSchema.safeParse({ question });
    if (!parsed.success) { setError("Enter a question of 1–2,000 characters, up to 3,000 UTF-8 bytes."); return; }
    if (agent.data?.mode === "fixture" && parsed.data.question !== FIXTURE_QUESTION) {
      setError("Scripted fixtures support the booking-confirmation question below. Live investigation requires operator configuration."); return;
    }
    submitting.current = true;
    setPending(true); setError(null); setReport(null);
    const active = new AbortController(); controller.current = active;
    try {
      const response = await fetch("/api/investigations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(parsed.data), signal: active.signal });
      if (!response.ok) throw new Error("request_failed");
      const result = await response.json() as ReadResult<Report>;
      if (!result.data) throw new Error("request_failed");
      setReport(result.data);
      await onComplete();
    } catch {
      if (!active.signal.aborted) setError("Investigation could not complete. Its backend work may still be draining; check records before submitting again.");
    } finally { if (!active.signal.aborted) { setPending(false); submitting.current = false; } }
  }
  return <section className="agent-panel" aria-labelledby="agent-title"><div className="agent-heading"><span className="agent-symbol"><TargetIcon /></span><span className="text-[10px] font-medium tracking-widest text-emerald-700">EVIDENCE BEFORE ANSWERS</span><span className="agent-mode-label">{agent.data?.mode === "fixture" ? "Scripted" : agent.data?.mode === "live" ? "Live mode" : agent.data ? "Disabled" : "Unavailable"}</span></div><h2 id="agent-title">Ask Reliability Agent</h2><p className="mt-2 text-[13px] leading-6 text-slate-500">Describe the symptom. Let the agent collect and connect the evidence.</p>
    <form className="mt-5" onSubmit={(e) => void submit(e)}><label className="mb-2 block text-xs font-medium text-slate-600" htmlFor="investigation-question">What needs investigating?</label><textarea id="investigation-question" value={question} maxLength={2000} disabled={pending || !enabled} aria-describedby="question-help question-error" aria-invalid={!!error} onChange={(e) => { setQuestion(e.target.value); setError(null); }} placeholder="Why are booking confirmations missing?" rows={3} /><p id="question-help" className="mt-2 text-[11px] leading-5 text-slate-400">{agent.data?.mode === "live" ? "Your question and restricted evidence will be sent to Nebius. Do not include credentials or customer data." : agent.data?.mode === "fixture" ? "Scripted fixture mode uses synthetic evidence. No live model or provider call." : "Investigation is unavailable until the backend policy is enabled and configured."}</p>
      {enabled && agent.data?.mode === "fixture" && <button type="button" className="question-chip" disabled={pending} onClick={() => setQuestion(FIXTURE_QUESTION)}><LightningBoltIcon className="size-3 shrink-0" />Use booking-confirmation question<ArrowRightIcon className="ml-auto size-3 shrink-0" /></button>}
      <button className="button-primary mt-4 w-full justify-center" disabled={!enabled || pending || !question.trim()}><TargetIcon className="size-4" />{pending ? "Following the evidence…" : "Investigate"}{!pending && <ArrowRightIcon className="ml-auto size-4" />}</button>
    </form>
    {!enabled && <div className="mt-4"><Notice>{!agent.data ? "Investigation policy is unavailable. Restore the backend connection." : agent.data.mode === "disabled" ? "Investigation is disabled by the backend. Enable fixture or live mode locally to use it." : "Investigation credentials are not configured."}</Notice></div>}
    <div id="question-error" className="mt-3 text-xs leading-5 text-rose-700" role="alert">{error}</div>
    {pending && <div className="investigation-progress" role="status"><div className="skeleton mb-3 h-2 rounded" /><p>Bounded to 6 model requests, 8 tools, and 120 seconds. Closing this page does not cancel backend work.</p></div>}
    <div className="agent-limits"><LockClosedIcon className="size-3 shrink-0" /><span>Bounded reads. Human-approved remediation.</span></div>
    {report && <div className="investigation-result" aria-live="polite"><div className="flex flex-wrap items-center gap-2"><Status value={report.status} /><span className="source">{report.inference_source === "scripted_fixture" ? "Scripted fixture" : humanize(report.inference_source)}</span></div><p className="mt-4 text-sm font-medium leading-6">{report.summary}</p>{report.reason && <p className="mt-2 text-xs text-slate-500">Reason: {humanize(report.reason)}</p>}<dl className="mt-4 grid gap-3 text-xs"><div><dt className="text-slate-400">Supported hypothesis</dt><dd className="mt-1 text-slate-700">{humanize(report.hypothesis ?? "unknown")}<span className="ml-1 text-slate-400">· Cause unverified</span></dd></div><div><dt className="text-slate-400">Evidence cited</dt><dd className="mt-1 font-mono">{report.cited_evidence_ids.join(", ") || "None"}</dd></div></dl>{report.next_steps.length > 0 && <div className="mt-4"><h3 className="text-xs font-medium">Recommended next steps</h3><ol className="mt-2 list-inside list-decimal space-y-2 text-xs leading-5 text-slate-500">{report.next_steps.map((step) => <li key={step}>{humanize(step)}</li>)}</ol></div>}<div className="mt-4 space-y-2">{report.evidence.map((e) => <Evidence key={e.id} label={`${e.id} · ${humanize(e.result.name ?? "Unavailable tool")} · ${e.result.status}`} value={e.result} />)}</div><p className="mt-4 text-[11px] leading-5 text-slate-400">{report.model_requests} model requests · {report.tool_calls} tool calls. No remediation executed. Root cause and customer outcomes remain unverified.</p></div>}
  </section>;
}
