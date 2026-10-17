import Link from "next/link";
import { ArrowRightIcon, ArrowTopRightIcon, CheckIcon, GlobeIcon, LayersIcon, LightningBoltIcon, LockClosedIcon, TargetIcon } from "@radix-ui/react-icons";
import { WorkflowPreview } from "@/components/workflow-preview";

export default function Page() {
  return <div className="landing">
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="landing-nav landing-width">
      <Link href="/" className="landing-brand" aria-label="Reliability home"><span className="landing-mark"><TargetIcon /></span>reliability<span className="brand-period">.</span></Link>
      <nav aria-label="Product navigation"><a href="#product">The product</a><a href="#how-it-works">How it works</a><a href="#boundaries">Built-in boundaries</a></nav>
      <Link href="/dashboard" className="landing-nav-action">Open dashboard<ArrowTopRightIcon /></Link>
    </header>
    <main id="main">
      <section className="landing-hero landing-width" aria-labelledby="hero-heading">
        <div className="hero-copy">
          <div className="landing-eyebrow"><span className="landing-live-dot" />AI RELIABILITY AGENT<span className="eyebrow-line" /></div>
          <h1 id="hero-heading">Your website is up.<br /><span>Is your business<br className="desktop-break" /> working?</span></h1>
          <p>Follow the failure beyond the homepage. Connect website signals, broken automations, and infrastructure evidence in one place.</p>
          <div className="hero-actions"><Link className="landing-button" href="/dashboard">Explore the workspace<ArrowRightIcon /></Link><a className="landing-link" href="#how-it-works">Follow an investigation<span>↘</span></a></div>
          <div className="hero-assurance"><LockClosedIcon />Evidence before conclusions. Your approval before action.</div>
          <div className="hero-index"><span>01 / OBSERVE THE WHOLE FLOW</span><span>SCROLL TO EXPLORE ↓</span></div>
        </div>
        <WorkflowPreview />
      </section>
      <section className="integration-strip" aria-label="Monitoring scope"><div className="landing-width"><p>ONE INVESTIGATION.<br /><strong>THE WHOLE PATH.</strong></p><span><GlobeIcon />Websites & APIs</span><span><LightningBoltIcon />n8n workflows</span><span><LayersIcon />Infrastructure</span><span className="strip-principle"><TargetIcon />Evidence, connected.</span></div></section>
      <section id="product" className="product-section landing-width">
        <div className="section-intro"><div><span className="landing-eyebrow">THE GAP BETWEEN UPTIME AND OUTCOME</span><h2>A green homepage.<br /><span>A broken booking flow.</span></h2></div><p>A site can load while a critical workflow fails further down the line. Reliability helps you see where the evidence stops—and where to look next.</p></div>
        <div className="product-grid">
          <article className="investigation-example"><div className="example-heading"><span><TargetIcon />INVESTIGATION WORKSPACE</span><span>ILLUSTRATIVE EXAMPLE</span></div><div className="example-question"><span>OPERATOR QUESTION</span><p>“Why are booking confirmations missing?”</p></div><div className="example-response"><span className="agent-monogram"><TargetIcon /></span><div><span className="response-label">FOLLOW THE EVIDENCE</span><p>The website responds. The booking workflow fails at the CRM step. The confirmation node has no successful execution evidence.</p><div className="evidence-tags"><span>Website observation</span><span>Execution evidence</span><span>Failed-node detail</span></div><div className="example-caveat"><span />Failure located. Root cause still unverified.</div></div></div><div className="example-footer"><span>OBSERVATIONS → CONTEXT → NEXT STEP</span><ArrowTopRightIcon /></div></article>
          <div className="product-principles"><article><span className="principle-number">01</span><div><h3>Signals with context.</h3><p>Read recorded observations alongside their source, timestamp, and supporting evidence.</p></div><GlobeIcon /></article><article><span className="principle-number">02</span><div><h3>Questions that do work.</h3><p>Use bounded investigation tools to inspect configured systems and support each recommendation.</p></div><LightningBoltIcon /></article><article><span className="principle-number">03</span><div><h3>Recovery that needs proof.</h3><p>A retry receipt is a starting point. Exact execution evidence must support scoped recovery.</p></div><CheckIcon /></article></div>
        </div>
      </section>
      <section id="how-it-works" className="method-section"><div className="landing-width"><div className="section-intro"><div><span className="landing-eyebrow">FROM SIGNAL TO SUPPORTED NEXT STEP</span><h2>Less guessing.<br /><span>A traceable path forward.</span></h2></div><Link href="/dashboard" className="landing-link">See the workspace<ArrowTopRightIcon /></Link></div><div className="method-steps">{[
          ["01", "Detect", "Persist the observation. Keep unhealthy, unknown, and failed checks distinct."],
          ["02", "Investigate", "Read configured systems. Connect evidence and cite supported findings."],
          ["03", "Approve", "Review the risk. Approve a specific, one-shot action through the operator CLI."],
          ["04", "Verify", "Inspect the exact new execution. Resolve only when the required proof passes."],
        ].map(([number, title, text]) => <article key={number}><span className="method-number">{number}<ArrowRightIcon /></span><h3>{title}<span>.</span></h3><p>{text}</p></article>)}</div></div></section>
      <section id="boundaries" className="boundaries-section landing-width"><div><span className="landing-eyebrow"><LockClosedIcon />CONTROL IS PART OF THE PRODUCT</span><h2>An agent with initiative.<br /><span>And boundaries.</span></h2><p>Useful autonomy needs a clear line between observing a system and changing it.</p><Link className="landing-link" href="/dashboard">Review the evidence<ArrowRightIcon /></Link></div><div className="boundary-list"><article><CheckIcon /><div><h3>Bounded tools. Explicit targets.</h3><p>No arbitrary shell, SQL, or remediation tools for the model.</p></div></article><article><CheckIcon /><div><h3>Your approval is specific.</h3><p>One action, a short approval window, and a durable audit trail.</p></div></article><article><CheckIcon /><div><h3>Uncertainty stays visible.</h3><p>A successful node does not prove customer delivery. Unsupported causes stay unknown.</p></div></article></div></section>
      <section className="landing-cta landing-width"><div className="cta-coordinate">RELIABILITY / OPERATOR WORKSPACE</div><div><h2>See the signal.<br /><span>Understand the failure.</span></h2><Link className="landing-button" href="/dashboard">Open the dashboard<ArrowTopRightIcon /></Link></div><p>Explore the operator application. Synthetic evidence is labeled inside the workspace; live integrations remain unverified.</p><TargetIcon className="cta-radar" aria-hidden="true" /></section>
    </main>
    <footer className="landing-footer landing-width"><Link href="/" className="landing-brand"><TargetIcon />reliability.</Link><p>Built for evidence. Operated by people.</p><span>AI RELIABILITY AGENT</span><a href="#main">Back to top ↑</a></footer>
  </div>;
}
