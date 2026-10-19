import type { Snapshot } from "@/lib/contracts";
import type { Monitoring } from "@/lib/monitoring";
import { age } from "@/lib/presentation";

export function ProjectGuide({ settings, data, now, onConnections }: {
  settings: Monitoring | null; data: Snapshot; now: number; onConnections?: () => void;
}) {
  const latestWebsite = [...(data.checks.data ?? [])].filter((check) => check.category === "website" && !check.synthetic)
    .sort((a, b) => Date.parse(b.observed_at) - Date.parse(a.observed_at))[0];
  const infrastructureCount = settings?.infrastructure.checks.filter((check) => check.configured).length ?? 0;
  const agent = data.agent.data;
  const parts = [
    { name: "Website", job: "Check whether your public site responds, its address resolves, and its certificate is valid.",
      state: !settings ? "Connection settings unavailable" : settings.websites.error ? "Storage needs attention" : settings.websites.targets.length ? "Ready for manual checks" : "Add a website below",
      next: latestWebsite ? `Latest website observation: ${age(latestWebsite.observed_at, now)}. Run checks for a fresh result.` : "Paste your website URL below, save it, then click Run checks." },
    { name: "n8n workflows", job: "Find recorded automation failures. A working website does not prove its workflows worked.",
      state: !settings ? "Connection settings unavailable" : settings.n8n_reports?.enabled ? "Failure reporting enabled" : settings.n8n.mode === "fixture" ? "Synthetic demo" : settings.n8n.configured ? "API configured; test access" : "Not connected to this app",
      next: settings?.n8n_reports?.enabled ? "Only received failure notifications are covered. No notifications does not mean healthy." : "Connect a supported n8n API account or set up its Error Trigger reporter. Cloud trials block the public API." },
    { name: "Infrastructure", job: "Inspect the hosting deployment and database services behind the site and automations.",
      state: !settings ? "Connection settings unavailable" : infrastructureCount ? `${infrastructureCount} of 5 checks configured` : "Not connected for monitoring",
      next: "Connect each provider you want to monitor. This app’s own history database is a separate connection." },
    { name: "Reliability Agent", job: "Use the available checks to investigate your question and explain findings with evidence.",
      state: !agent ? "Status unavailable" : agent.mode === "disabled" ? "AI investigation is off" : agent.mode === "fixture" ? "Scripted demo" : agent.configured ? "Live mode configured; test required" : "AI credentials missing",
      next: "Live AI needs a Nebius key and available credits. It cannot inspect a system that has no connection." },
  ];
  return <section className="panel p-6" aria-labelledby="project-guide-title">
    <p className="eyebrow">WHAT THIS PROJECT DOES</p><h2 id="project-guide-title" className="mt-2 text-xl font-medium">Three things to check. One agent to investigate.</h2>
    <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">Your website, n8n workflows, and infrastructure are the systems being watched. This dashboard is the screen you control. The backend runs checks and saves evidence. The Reliability Agent uses that evidence to answer questions.</p>
    <div className="mt-4 flex flex-wrap gap-3"><a href="#website-setup" className="button-primary">Go to website checks</a>{onConnections && <button className="button-secondary" onClick={onConnections}>Set up n8n, infrastructure and AI</button>}</div>
    <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">{parts.map((part, index) => <article key={part.name} className="rounded-xl border border-slate-800 p-4"><p className="text-xs text-slate-400">0{index + 1}</p><h3 className="mt-2 text-base font-medium">{part.name}</h3><p className="mt-2 text-sm leading-6 text-slate-400">{part.job}</p><p className="mt-3 text-sm font-medium">{part.state}</p><p className="mt-2 text-xs leading-5 text-slate-400">{part.next}</p></article>)}</div>
    <div className="mt-5 border-t border-slate-800 pt-4 text-xs leading-6 text-slate-400"><p><strong className="text-slate-200">Current operation:</strong> checks run when requested. Refresh records only reloads saved results. There is no continuous monitoring schedule.</p><p><strong className="text-slate-200">Incident recording:</strong> {data.storage.data ? data.storage.data.automatic_incidents ? "On for saved unhealthy observations." : "Off. Failures can be saved without creating an incident." : "Status unavailable."} No incidents does not prove everything works.</p><p><strong className="text-slate-200">Repair actions:</strong> production retries and recovery actions are unavailable in this dashboard.</p></div>
    <details className="mt-4 text-xs leading-6 text-slate-400"><summary>Where the frontend, backend and database live</summary><p className="mt-2">Vercel serves this frontend: the pages and buttons. Render runs the Python backend: the checks, connection rules and investigator. Supabase stores this app’s history. The screen calls the backend securely; provider keys stay on the backend.</p></details>
  </section>;
}
