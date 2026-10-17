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
    <div className="preview-caption"><span><span className="small-square" />A CONNECTED VIEW</span><span>Illustrative example</span></div>
    <div className="flow-canvas" aria-label="Illustrative workflow: website and infrastructure observations inform an investigation of the failed booking workflow">
      <div className="flow-inputs"><div className="flow-node"><span className="flow-icon"><GlobeIcon /></span><div><strong>Website</strong><span>Endpoint responds</span></div><CheckIcon className="flow-check" /></div><div className="flow-node"><span className="flow-icon"><LayersIcon /></span><div><strong>Infrastructure</strong><span>Supporting evidence</span></div><LayersIcon className="flow-check" /></div></div>
      <div className="flow-connector" aria-hidden="true"><span /><span /></div>
      <div className="flow-agent"><span className="agent-core"><TargetIcon /></span><div><strong>Reliability Agent</strong><span>Connect the evidence. Identify the next step.</span></div><span className="agent-read-label">READ ONLY</span></div>
      <div className="flow-connector connector-single" aria-hidden="true"><span /></div>
      <div className="flow-node node-workflow"><span className="flow-icon"><LightningBoltIcon /></span><div><strong>Booking workflow</strong><span>CRM step failed · Confirmation not observed</span></div><span className="node-alert">!</span></div>
    </div>
    <div className="preview-report" aria-live="polite" aria-atomic="true"><div className="report-status"><span />{step.label}<span className="report-index">{String(selected + 1).padStart(2, "0")} / 04</span></div><h2>{step.title}</h2><p>{step.detail}</p><div className="execution-chain"><span><CheckIcon />Trigger</span><i /><span><CheckIcon />Calendar</span><i /><span className="chain-failed">! CRM</span><i /><span className="chain-pending">Confirmation</span></div></div>
    <div className="preview-controls" role="group" aria-label="Explore the illustrative workflow stages">{steps.map((item, index) => <button type="button" key={item.name} aria-pressed={selected === index} onClick={() => setSelected(index)}><span>{index === 2 ? <LockClosedIcon /> : index === 3 ? <CheckIcon /> : <span className="step-index">0{index + 1}</span>}</span>{item.name}{selected === index && <ArrowRightIcon />}</button>)}</div>
    <div className="preview-disclaimer"><LockClosedIcon />Example only · No checks or actions are executed here.</div>
  </div>;
}
