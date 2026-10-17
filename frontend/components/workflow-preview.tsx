"use client";

import { useState } from "react";
import { ArrowRightIcon, CheckIcon, GlobeIcon, LayersIcon, LightningBoltIcon, LockClosedIcon, TargetIcon } from "@radix-ui/react-icons";

const steps = [
  { name: "Detect", title: "A workflow needs attention", detail: "The CRM step failed. A successful confirmation has not been observed.", label: "FAILURE OBSERVED", kind: "detect" },
  { name: "Investigate", title: "Separate the signal from the noise", detail: "The website responds. Execution evidence points to the CRM step; the cause still needs proof.", label: "EVIDENCE CONNECTED", kind: "investigate" },
  { name: "Approve", title: "A recommendation is yours to review", detail: "Retrying may repeat external effects. Approval and execution stay in the operator CLI.", label: "OPERATOR DECISION", kind: "approve" },
  { name: "Verify", title: "A receipt is not recovery", detail: "Required nodes in the exact new execution must succeed before scoped resolution.", label: "PROOF REQUIRED", kind: "verify" },
];
export function WorkflowPreview() {
  const [selected, setSelected] = useState(0);
  const step = steps[selected];
  return <div className={`workflow-preview stage-${step.kind}`}>
    <div className="preview-grid" aria-hidden="true" />
    <div className="preview-caption"><span><span className="small-square" />WORKFLOW INTELLIGENCE</span><span>ILLUSTRATIVE PREVIEW</span></div>
    <div className="flow-canvas" aria-label="Illustration: website signals and infrastructure evidence connect to the reliability agent, which inspects an n8n workflow failure">
      <svg className="flow-lines" viewBox="0 0 570 320" fill="none" aria-hidden="true"><path d="M113 73H230Q260 73 260 105V154M113 238H230Q260 238 260 205V154M260 154H337Q365 154 365 184V238H430" /><path className="flow-active-line" d="M113 73H230Q260 73 260 105V154H337Q365 154 365 184V238H430" /></svg>
      <div className="flow-node node-website"><span className="flow-icon"><GlobeIcon /></span><div><strong>Website</strong><span>Endpoint responds</span></div><span className="node-dot" /></div>
      <div className="flow-node node-infra"><span className="flow-icon"><LayersIcon /></span><div><strong>Infrastructure</strong><span>Supporting evidence</span></div><span className="node-dot muted-dot" /></div>
      <div className="flow-agent"><span className="agent-orbit orbit-one" /><span className="agent-orbit orbit-two" /><span className="agent-core"><TargetIcon /></span><span className="flow-agent-label">RELIABILITY AGENT</span></div>
      <div className="flow-node node-workflow"><span className="flow-icon"><LightningBoltIcon /></span><div><strong>Booking workflow</strong><span>CRM step failed</span></div><span className="node-alert">!</span></div>
      <span className="flow-packet packet-one" aria-hidden="true" /><span className="flow-packet packet-two" aria-hidden="true" />
      <div className="flow-coordinates"><span>WEBSITE</span><span>AUTOMATION</span><span>INFRASTRUCTURE</span></div>
    </div>
    <div className="preview-report" aria-live="polite" aria-atomic="true"><div className="report-status"><span />{step.label}<span className="report-index">{String(selected + 1).padStart(2, "0")} / 04</span></div><h2>{step.title}</h2><p>{step.detail}</p><div className="execution-chain"><span><CheckIcon />Trigger</span><i /><span><CheckIcon />Calendar</span><i /><span className="chain-failed">! CRM</span><i /><span className="chain-pending">Confirmation</span></div></div>
    <div className="preview-controls" role="group" aria-label="Explore the illustrative workflow stages">{steps.map((item, index) => <button type="button" key={item.name} aria-pressed={selected === index} onClick={() => setSelected(index)}><span>{index === 2 ? <LockClosedIcon /> : index === 3 ? <CheckIcon /> : <span className="step-index">0{index + 1}</span>}</span>{item.name}{selected === index && <ArrowRightIcon />}</button>)}</div>
    <div className="preview-disclaimer"><LockClosedIcon />Example only · No checks or actions are executed here.</div>
  </div>;
}
